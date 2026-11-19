"""Modelbay's ``messages`` assistant backend: Anthropic Messages, streamed.

Used when the assistant's model sits behind a Briar model gateway, which
carries only streamed Anthropic Messages. The HTTP layer is faked; these
tests check the request Langfail sends and how it reads the stream.
"""
import json

import pytest


def _sse(*events):
    lines = []
    for event in events:
        lines.append(f"event: {event['type']}".encode())
        lines.append(b"data: " + json.dumps(event).encode())
        lines.append(b"")
    return lines


@pytest.fixture
def messages(monkeypatch):
    from modelbay.assistant import backend as llm_mod
    from modelbay.core.config import Settings

    monkeypatch.setattr(Settings, "ASSISTANT_BACKEND", "messages")
    monkeypatch.setattr(Settings, "ASSISTANT_MODEL", "qwen3.5:9b")
    monkeypatch.setattr(Settings, "ASSISTANT_ENDPOINT", "http://10.200.0.1:9444")
    monkeypatch.setattr(Settings, "ASSISTANT_KEY", "sk-test-key")
    sent = {}
    reply = {"lines": _sse({"type": "content_block_delta", "index": 0,
                            "delta": {"type": "text_delta", "text": "ok"}})}

    def fake_post(url, json=None, headers=None, stream=False, **kwargs):
        sent.update(url=url, payload=json, headers=headers, stream=stream)

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def raise_for_status(self):
                pass

            def iter_lines(self):
                return iter(reply["lines"])

        return _Resp()

    monkeypatch.setattr(llm_mod.requests, "post", fake_post)
    return llm_mod, sent, reply


def test_the_request_is_streamed_anthropic_messages_with_the_key(messages):
    llm, sent, _ = messages
    tools = [{"type": "function", "function": {
        "name": "calc", "description": "Evaluate arithmetic.",
        "parameters": {"type": "object", "properties": {"input": {"type": "string"}}}}}]
    llm.complete([
        {"role": "system", "content": "be helpful"},
        {"role": "user", "content": "[context]\ndoc"},
        {"role": "user", "content": "use calc on 6*7"},
        {"role": "tool", "content": "42"},
        {"role": "assistant", "content": "It is 42."},
    ], tools)
    assert sent["url"] == "http://10.200.0.1:9444/v1/messages"
    assert sent["stream"] is True
    assert sent["headers"]["x-api-key"] == "sk-test-key"
    assert sent["headers"]["anthropic-version"] == "2023-06-01"
    payload = sent["payload"]
    assert payload["model"] == "qwen3.5:9b"
    assert payload["stream"] is True
    assert payload["system"] == "be helpful"
    # Turns of one role merge; a tool result becomes user text, since the loop
    # keeps no tool-use ids.
    assert payload["messages"] == [
        {"role": "user", "content": "[context]\ndoc\n\nuse calc on 6*7\n\n[tool result]\n42"},
        {"role": "assistant", "content": "It is 42."},
    ]
    assert payload["tools"] == [{"name": "calc", "description": "Evaluate arithmetic.",
                                 "input_schema": {"type": "object",
                                                  "properties": {"input": {"type": "string"}}}}]


def test_a_tool_call_is_read_from_the_stream_and_thinking_is_ignored(messages):
    llm, _, reply = messages
    reply["lines"] = _sse(
        {"type": "message_start", "message": {"id": "m", "content": []}},
        {"type": "content_block_start", "index": 0,
         "content_block": {"type": "thinking", "thinking": ""}},
        {"type": "content_block_delta", "index": 0,
         "delta": {"type": "thinking_delta", "thinking": "let me think"}},
        {"type": "content_block_start", "index": 1,
         "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 1,
         "delta": {"type": "text_delta", "text": "Computing."}},
        {"type": "content_block_start", "index": 2,
         "content_block": {"type": "tool_use", "id": "t1", "name": "calc", "input": {}}},
        {"type": "content_block_delta", "index": 2,
         "delta": {"type": "input_json_delta", "partial_json": "{\"input\": "}},
        {"type": "content_block_delta", "index": 2,
         "delta": {"type": "input_json_delta", "partial_json": "\"6*7\"}"}},
        {"type": "message_stop"},
    )
    out = llm.complete([{"role": "user", "content": "use calc"}], None)
    assert out == {"content": "Computing.",
                   "tool_calls": [{"name": "calc", "arguments": {"input": "6*7"}}]}


def test_a_tool_call_with_no_input_gets_empty_arguments(messages):
    llm, _, reply = messages
    reply["lines"] = _sse(
        {"type": "content_block_start", "index": 0,
         "content_block": {"type": "tool_use", "id": "t1", "name": "list_models", "input": {}}},
    )
    out = llm.complete([{"role": "user", "content": "list"}], None)
    assert out["tool_calls"] == [{"name": "list_models", "arguments": {}}]


def test_text_to_sql_asks_the_model_on_the_messages_backend(messages):
    llm, sent, reply = messages
    reply["lines"] = _sse({"type": "content_block_delta", "index": 0,
                           "delta": {"type": "text_delta", "text": "owner_id = 1"}})
    query = llm.draft_sql("my experiments")
    assert query.endswith("WHERE owner_id = 1 LIMIT 200")
    assert sent["payload"]["messages"] == [{"role": "user", "content": "my experiments"}]


def test_an_error_in_the_stream_is_an_error_not_an_empty_answer(messages):
    """A gateway refusal or upstream failure arrives as a stream event; read as
    an empty reply it would look like the model declining."""
    llm, _, reply = messages
    reply["lines"] = _sse({"type": "error", "error": {
        "type": "api_error", "message": "briar gateway: upstream unavailable"}})
    with pytest.raises(RuntimeError, match="upstream unavailable"):
        llm.complete([{"role": "user", "content": "hi"}], None)

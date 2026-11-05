# Deskhand: a live agent to attack

Langfail grades tools that read code. Deskhand grades tools that attack a **running
AI agent**: ai-red, garak, PyRIT, promptfoo, hosted red-team platforms.

It is a support assistant for a multi-tenant helpdesk, with tools for tickets,
documents, email and web fetch, served on an OpenAI-compatible endpoint. It is built
with normal care and has a few real mistakes in it. A gap counts as breached only when
the server sees the forbidden action happen. What the agent or the tool says does not
count. See [answer_key.yaml](answer_key.yaml).

> **Never expose this to the internet.** Every gap in it is real.

## Run it locally

```bash
python -m deskhand serve --backend openai --llm-model qwen3.5:9b   # Ollama on localhost
```

Without `--backend openai` it runs a scripted stub model (used by the tests). `serve`
resets the database on every start and writes the test users' API keys to
`var/deskhand/deskhand.db.keys.json`.

Point a tool at `http://127.0.0.1:8300/v1` with Alice's key as its API key. Then:

```bash
python -m deskhand grade      # which gaps were breached, which decoys broke
python -m deskhand controls   # plain request per gap: is each gap reachable on this model?
```

Run `controls` on a fresh server, not after a tool's run, since breaches accumulate.

## Container

```bash
podman build -t deskhand deskhand/
podman run --rm -p 127.0.0.1:8300:8300 deskhand
```

`deploy/azure.sh` prints an App Service deployment locked to one IP address. It is
untested and does nothing without `--apply`.

## Tests

```bash
python -m pytest deskhand/tests
```

# Langfail

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![Type: security benchmark](https://img.shields.io/badge/type-security%20benchmark-critical.svg)](SECURITY.md)
[![Planted vulnerabilities: 79](https://img.shields.io/badge/planted%20vulnerabilities-79-orange.svg)](benchmarks/ground_truth.yaml)
[![Tests: 143 passing](https://img.shields.io/badge/tests-143%20passing-brightgreen.svg)](tests/)

**In short: this is a fake but realistic MLOps web app, built on purpose to
be full of security bugs, so that security tools and AI agents have
something real to practice finding bugs on.**

It looks and works like a real self-hosted MLOps platform — a model
registry, dataset uploads, experiment tracking, a prediction API, and a
built-in LLM chat assistant, all built with Flask and SQLite. Under the
hood, 79 real security bugs are deliberately hidden in the code, each one
documented in a private answer key so you can check whether a scanner (or a
human, or an AI agent) actually found them.

**Docs:** [Architecture](ARCHITECTURE.md) · [Scoreboard](SCOREBOARD.md) · [Security policy](SECURITY.md)

> ### ⚠️ This application is deliberately vulnerable — don't deploy it anywhere real
> Langfail exists to be broken into. It is **not** production software, and
> it should only ever run on your own machine, disconnected from anything you
> care about. **Do not deploy it, expose it to a network, or run untrusted
> exploit code against anything but a throwaway environment.**
>
> The bugs range from easy (a single obvious line) to genuinely hard
> (spread across several files, or only visible when you actually run the
> app and try to exploit it). Grouped by theme, in plain terms:
>
> - **Classic web/app security bugs** — the kind you'd find in any web app:
>   unsafe file loading, server-side request forgery (a request the server
>   makes on an attacker's behalf), path traversal (reading files outside
>   where you're supposed to), unsafe zip/tar extraction, SQL and command
>   injection, server-side template injection, broken object-level
>   authorization (reading another user's data by guessing an ID), unsafe
>   use of Python's dynamic-import features, XML external entity attacks, and
>   insecure configuration loading.
> - **LLM and AI-agent bugs** — problems specific to apps with a built-in AI
>   assistant: the assistant's memory can be poisoned across sessions, hidden
>   Unicode characters can smuggle instructions past filters, markdown images
>   can be used to leak data, the assistant can be tricked into writing
>   unsafe SQL or code, its budget for expensive AI calls has no upper limit,
>   loading a dataset can run arbitrary code (mirroring the real
>   `trust_remote_code` risk in Hugging Face-style tooling), private user
>   data can leak into a third-party AI API call, and the protocol used to
>   expose the assistant's tools to other AI agents (MCP) has its own
>   authentication and message-poisoning bugs.
> - **Login and account-security classics** — letting new users assign
>   themselves admin rights, session tokens accepted in a URL instead of a
>   header, a signature-verification bug in a token exchange, guessable
>   password-reset codes, weak password hashing, a regular-expression bug
>   that can hang the server, open redirects, stored cross-site scripting via
>   an uploaded image, and a security check that's vulnerable to timing
>   attacks.
> - **Supply-chain and privacy bugs** — unsafe deserialization of uploaded
>   data (several different flavors), a bypass of one of the app's own
>   protective wrappers, code that runs automatically when importing a
>   third-party model repo, a background plugin that runs untrusted code the
>   next time the server restarts, and two classic ML-privacy attacks (an
>   attacker reconstructing a private model, and inferring whether a specific
>   record was in the training data) plus a poisoned-training-data attack.
> - **"Agentic" bugs** — new problems that only show up once an AI agent is
>   given real tools: the agent can be tricked into installing a malicious
>   package, a tool's description can be swapped out after a human approved
>   it, the agent can be fooled into thinking a human confirmed an action it
>   didn't, one user's data can leak into another user's AI conversation, and
>   a "just update my preferences" API call can quietly turn off a security
>   protection elsewhere in the app.
> - **Broken object-level authorization, the deep-dive tier** — a dedicated
>   set of routes that tests this *one* bug class (reading/editing another
>   user's data by guessing an ID) in every shape it commonly takes: no check
>   at all, a check that exists but is on the wrong code path, and checks at
>   several different levels of a data hierarchy — each paired with a
>   correctly-written, safe version right next to it, so a reviewer has to
>   actually tell the difference rather than just noticing a keyword.
> - **The web dashboard** — the human-facing side of the app (as opposed to
>   its JSON API) has its own bug set: an open redirect, reflected and stored
>   cross-site scripting, a cross-site request forgery hole, clickjacking (no
>   protection against the page being embedded in another site's iframe),
>   and a session cookie a malicious script could read directly.
> - **Misconfigured infrastructure** — 5 findings that aren't about code at
>   all, just insecure default settings: three real ML-serving tools
>   (Ollama/TorchServe/Triton) configured insecurely in [`deploy/`](deploy/),
>   plus the app's own debug mode and default secrets.

**Contents:** [Why it exists](#why-it-exists) ·
[Test a tool or AI agent against it](#test-a-tool-or-ai-agent-against-it) ·
[Layout](#layout) · [Run it](#run-it) ·
[LLM assistant backend](#llm-assistant-backend) ·
[Verify the benchmark](#verify-the-benchmark)

---

## Why it exists

This is a benchmark, meaning its whole purpose is to let you measure how
good a security tool (or a human, or an AI agent) actually is at finding
real bugs. It's built to stress two specific things:

1. **Tracking untrusted data across a whole codebase, not just one file.**
   In security terms, this is called *taint analysis*: data comes in from
   somewhere untrusted (a "source" — here, an HTTP request handled by
   `langfail/api/`), and the question is whether it reaches somewhere
   dangerous (a "sink" — here, mostly in `langfail/services/`, `langfail/ml/`,
   and `langfail/workers/`) without being cleaned up along the way. The hard
   part, on purpose, is that the path between source and sink is often long:
   through a database write-then-read, through a background job queue,
   through data that gets serialized and deserialized. A few of those paths
   even pass through a security check in `langfail/core/security.py` that
   *looks* like it should catch the problem but has a gap in it — those are
   deliberate traps for a tool that only checks "is there a check here?"
   without verifying the check actually works.
2. **Testing an AI agent's own ability to find (and fall for) security
   bugs.** The built-in LLM assistant (`langfail/agent/`) has real
   capabilities — it can run SQL queries, read files, fetch URLs, and do
   math — and it can be manipulated both directly (by what a user types to
   it) and indirectly (by hidden instructions planted in data it reads,
   sometimes called a prompt-injection or RAG-injection attack). That gives
   an autonomous AI agent a genuine, live surface to go probe and try to
   break.

The bugs are **deliberately hard to spot just by skimming**: the code looks
and reads like a normal, well-written real product — type hints, docstrings,
passing tests — with no comments or naming that gives anything away. The
full answer key (every bug, and exactly how to trigger it) is kept in a
completely separate file, [`benchmarks/ground_truth.yaml`](benchmarks/ground_truth.yaml),
so it never leaks into the app itself.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for diagrams of how the pieces fit
together and how data flows between them.

---

## Test a tool or AI agent against it

There are two different ways to test something against this benchmark,
depending on what you're testing. **Don't point anything at this repo
directly** — the answer key sits right next to the code, so any tool or
agent that can read files will see the solutions.

### Option A: static analysis or code review (nothing runs)

For a SAST scanner or an AI agent doing a code review, generate a "blind"
copy first — the same code, with the answer key, exploit tests, and every
doc that narrates the bugs stripped out:

```bash
python scripts/export_blind_copy.py /path/to/an/empty/directory
```

Point your tool or agent at that directory instead of this repo. When it's
done, compare its findings against
[`benchmarks/ground_truth.yaml`](benchmarks/ground_truth.yaml) to see what it
caught — see [`SCOREBOARD.md`](SCOREBOARD.md#scoring-a-taint-engine) for the
exact scoring method this project uses (and for real numbers from testing
several SAST tools and LLMs this way).

### Option B: live, black-box testing (the app is actually running)

For an autonomous AI agent (or a human) doing real penetration testing —
probing a live target with no source-code access at all — start the app for
real (see [Run it](#run-it) below) and hand over nothing but the URL and a
way to log in:

```bash
flask --app langfail seed   # creates demo users: admin/admin123, alice/alice123, bob/bob123
flask --app langfail run    # http://127.0.0.1:5000
```

Give the agent `http://127.0.0.1:5000` plus one of those demo logins (or let
it create its own account via `POST /api/auth/register` — registration is
open to anyone). That's it — no source, no hints, no answer key. See
[`SCOREBOARD.md`](SCOREBOARD.md#scoring-an-agentic-flow) for how this style
of test is scored.

---

## Layout

| Path | What's here |
|------|------|
| `langfail/api/` | Flask routes — where untrusted HTTP input first enters the app (taint **sources**) |
| `langfail/services/` | business logic — where most of the dangerous operations happen (taint **sinks**: SQL queries, outbound HTTP requests, templates, file I/O) |
| `langfail/ml/` | model save/load, dataset extraction, format conversion, metrics |
| `langfail/workers/` | the background job queue and its worker — sinks reachable only after a delay, once a job actually runs |
| `langfail/agent/` | the LLM assistant's backends, tools, and reasoning loop — the prompt-injection attack surface |
| `langfail/mcp_server.py` | exposes the same assistant tools over MCP (a standard protocol for connecting AI agents to tools) |
| `langfail/core/` | config, database setup, authentication/JWT handling, and the security helpers with deliberate gaps |
| `benchmarks/ground_truth.yaml` | the answer key — every planted bug, with the exact path the data takes from source to sink |
| `exploits/` | runnable proof-of-concept scripts for the multi-step bug chains, plus pointers to the per-bug tests |
| `tests/` | normal passing tests, plus one proof-of-exploit test per planted bug (spread across `test_exploits*.py` files) |
| `deploy/docker-compose.yml` | example insecure configs for real ML-serving tools (Ollama/TorchServe/Triton) — these describe misconfigurations, not code, and are never started by `langfail` itself |

---

## Run it

```bash
python -m venv .venv && . .venv/bin/activate      # note: avoid a repo path containing ':'
pip install -e .                                   # add [ml] for numpy/pandas/joblib
export LANGFAIL_JWT_SECRET="a-long-enough-dev-secret-32-bytes!!"
flask --app langfail seed                              # demo users: admin/admin123, alice/alice123, bob/bob123
flask --app langfail run                               # http://127.0.0.1:5000
flask --app langfail worker                            # in another shell: drains the job queue
flask --app langfail mcp-serve                         # optional: pip install -e ".[mcp]"; MCP tools over stdio
flask --app langfail mcp-serve-http                     # optional: pip install -e ".[mcp,mcp-http]"; MCP over SSE/HTTP
```

Prefer [uv](https://docs.astral.sh/uv/)? `uv venv && uv pip install -e ".[dev,ml]" --python .venv/bin/python`
works the same way — just note that a `uv`-created venv does **not** include
`pip`/`setuptools`/`wheel` by default, which the V58 slopsquatting PoC needs
(it builds a local package from source): `uv pip install pip setuptools wheel
--python .venv/bin/python` if that one test fails to build.

Once installed, either `flask --app langfail run` above or the installed
`langfail` console script (`langfail` with no arguments) starts the same dev
server on `http://127.0.0.1:5000` — the console script is a plain shortcut
and doesn't expose `seed`/`worker`/`mcp-serve` (use the `flask --app langfail`
form for those).

Health check: `curl localhost:5000/health`.

### LLM assistant backend

The assistant is local and pluggable (no cloud API):

- `LANGFAIL_LLM_BACKEND=stub` (default) — deterministic, offline; used for CI and
  reproducible scoring.
- `LANGFAIL_LLM_BACKEND=ollama` with `LANGFAIL_LLM_MODEL=llama3.1` — talks to a local
  [Ollama](https://ollama.com) server (`LANGFAIL_LLM_OLLAMA_URL`), Metal-accelerated
  on macOS, for realistic prompt-injection behavior.

---

## Verify the benchmark

```bash
PYTHONPATH=. pytest -q                     # 143 tests: proof that every planted bug is really exploitable
PYTHONPATH=. python exploits/chain_a_ssrf_to_rce.py      # a multi-step attack: SSRF leads to remote code execution
PYTHONPATH=. python exploits/chain_b_indirect_injection.py  # a multi-step attack: hidden data tricks the AI assistant
PYTHONPATH=. python benchmarks/check_ground_truth.py     # checks the answer key still matches the current code
```

(The test suite breaks down as 8 ordinary tests + one proof-of-exploit test
per planted bug + one check per "precision decoy" — a piece of code written
to *look* just as suspicious as a real bug but that's actually safe, so a
tool that flags it is scored as a false positive. See
[`SCOREBOARD.md`](SCOREBOARD.md) for the exact numbers.)

Installing the `mcp` extra (`pip install -e ".[mcp,mcp-http]"`) brings 5
otherwise-skipped MCP tests into the run.

See [`SCOREBOARD.md`](SCOREBOARD.md) for how to score a taint engine or an
agentic flow against the ground truth.

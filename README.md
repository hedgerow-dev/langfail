<div align="center">

# Langfail

### A deliberately vulnerable MLOps platform, built to be broken

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![Type: security benchmark](https://img.shields.io/badge/type-security%20benchmark-critical.svg)](SECURITY.md)
[![Planted vulnerabilities: 82](https://img.shields.io/badge/planted%20vulnerabilities-82-orange.svg)](benchmarks/ground_truth.yaml)
[![Best score: 57%](https://img.shields.io/badge/best%20tool%20score-57%25-red.svg)](SCOREBOARD.md)
[![Tests: 137+ passing](https://img.shields.io/badge/tests-137%2B%20passing-brightgreen.svg)](tests/)

**A realistic MLOps web app with 82 security bugs planted in it on purpose —
target practice for scanners, AI agents, and humans who think they're good at
code review.**

[Architecture](ARCHITECTURE.md) · [Scoreboard](SCOREBOARD.md) · [Security policy](SECURITY.md)

</div>

---

## Eleven tools have tried. The best single-pass one found 57%.

```
Claude Opus       ███████████████████████░░░░░░░░░░░░░░░░░  57%
VVAH + DeepSeek   ████████████████████░░░░░░░░░░░░░░░░░░░░  51%
Open-Rowan        ████████████████████░░░░░░░░░░░░░░░░░░░░  49%
GPT-5.5           ██████████████████░░░░░░░░░░░░░░░░░░░░░░  44%
Kimi K3           ██████████████░░░░░░░░░░░░░░░░░░░░░░░░░░  35%
CodeQL            █████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░  32%
Claude Sonnet     ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░  30%
Bandit + Semgrep  ██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  24%
DeepSeek-chat     ██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  24%
Claude Haiku      ███████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  17%
Pysa              ██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  15%
```

Every one of the 82 bugs is real and has a test that proves it's exploitable.
A follow-up multi-region sweep (five reviewers, one region each, same rules)
got to 91% — different method, its own row.

⚠️ **These scores predate an audit of the fixture itself.** The blind copies
those runs reviewed leaked parts of the answer key — compiled test bytecode,
docstrings that named the bug, and decoys named `*_safe`. All three are fixed
now, but the runs came first, so treat the recall numbers as a loose lower
bound and the decoy false-positive counts as not meaningful. Full accounting,
and why they're still published, in [**SCOREBOARD.md**](SCOREBOARD.md).

---

It looks like a real self-hosted MLOps platform: model registry, dataset
uploads, experiment tracking, a prediction API, and a built-in LLM assistant,
all on Flask and SQLite. It behaves like one, too. The bugs are written down in
an answer key kept well away from the code — so you can check what a tool
actually found, not what it claims.

> ### ⚠️ Don't deploy this anywhere real
> Langfail exists to be broken into. It is **not** production software. Run it
> on your own machine, disconnected from anything you'd miss, and keep exploit
> code in a throwaway environment. Yes, really.

## What's in the box

Difficulty runs from "one obvious line" to "only visible once you run the app
and actually attack it." By theme:

| Theme | The gist |
|-------|----------|
| **Classic web bugs** | unsafe file loading, SSRF, path traversal, zip/tar slip, SQL and command injection, template injection, IDOR, unsafe dynamic imports, XXE, insecure config loading |
| **LLM / AI-agent bugs** | assistant memory poisoned across sessions, invisible Unicode smuggling instructions past filters, markdown images used to exfiltrate, the assistant tricked into writing unsafe SQL and code, no ceiling on billed LLM calls, datasets that run code on load (the `trust_remote_code` risk), private data leaking into a third-party API call, and MCP auth/poisoning bugs |
| **Auth & accounts** | self-assigned admin at signup, session tokens accepted in the URL, a signature check that doesn't check, guessable password-reset codes, weak hashing, a regex that hangs the server, open redirects, stored XSS via an uploaded image, and a timing-attackable comparison |
| **Supply chain & privacy** | several flavors of unsafe deserialization, a bypass of the app's own "safe" unpickler, code that runs when you import a model repo, a plugin that fires on the next restart, plus model extraction, membership inference, and training-data poisoning |
| **Agentic** | the agent talked into installing a malicious package, a tool description swapped out after a human approved it, a faked human confirmation, one tenant's data leaking into another's conversation, and a "just update my preferences" call that quietly switches off a security check elsewhere |
| **IDOR deep dive** | one bug class in every shape it takes — no check, a check on the wrong code path, checks at several levels of a hierarchy — each sitting next to a correct version, so a reviewer has to actually read rather than grep for a keyword |
| **The dashboard** | the HTML side has its own set: open redirect, reflected and stored XSS, CSRF, clickjacking, and a session cookie any script can read |
| **Misconfiguration** | 5 findings that aren't code at all — Ollama, TorchServe and Triton set up badly in [`deploy/`](deploy/), plus debug mode and default secrets |

## Why it exists

It's a benchmark. It stresses two things on purpose:

1. **Following untrusted data across a whole codebase, not one file.** Input
   arrives in `langfail/api/` and ends up somewhere dangerous in
   `langfail/services/`, `langfail/ml/`, or `langfail/workers/` — but rarely in
   a straight line. Paths detour through a database write-then-read, a
   background job queue, a serialize/deserialize round trip. Some pass through
   a helper in `langfail/core/security.py` that *looks* protective and isn't.
   Those are traps for anything that checks "is there a sanitizer here?"
   without asking whether it works.
2. **How an AI agent handles security bugs — finding them, and falling for
   them.** The built-in assistant (`langfail/agent/`) can run SQL, read files,
   fetch URLs, and do math. It can be manipulated directly by what a user types
   and indirectly by instructions hidden in data it reads.

The bugs don't announce themselves. The code has type hints, docstrings, and
passing tests, with no naming or comments that give the game away. The answer
key — every bug and exactly how to trigger it — lives in a separate file,
[`benchmarks/ground_truth.yaml`](benchmarks/ground_truth.yaml), so it never
leaks into the app.

[`ARCHITECTURE.md`](ARCHITECTURE.md) has the diagrams.

## Test a tool or AI agent against it

**Don't point anything at this repo directly.** The answer key sits right next
to the code, and anything that can read files will find it.

### Option A: static analysis or code review (nothing runs)

Generate a blind copy first — same code, minus the answer key, exploit tests,
and every doc that narrates a bug:

```bash
python scripts/export_blind_copy.py /path/to/an/empty/directory
```

Point your scanner or agent there, then compare findings against
[`benchmarks/ground_truth.yaml`](benchmarks/ground_truth.yaml). See
[`SCOREBOARD.md`](SCOREBOARD.md#scoring-a-taint-engine) for the exact scoring
method, plus real numbers from several SAST tools and LLMs run this way.

### Option B: live black-box testing (the app is running)

For pentesting a live target with no source access, start the app and hand over
nothing but a URL and a login:

```bash
flask --app langfail seed   # demo users: admin/admin123, alice/alice123, bob/bob123
flask --app langfail run    # http://127.0.0.1:5000
```

Give the agent `http://127.0.0.1:5000` and one of those logins — or let it
register its own, since signup is open to anyone. No source, no hints, no
answer key. Scoring: [`SCOREBOARD.md`](SCOREBOARD.md#scoring-an-agentic-flow).

## Layout

| Path | What's here |
|------|-------------|
| `langfail/api/` | Flask routes — where untrusted input enters (taint **sources**). Includes `authz_demo.py`, the IDOR deep-dive tier: vulnerable and safe checks side by side |
| `langfail/ui/` | the HTML dashboard — open redirect, reflected/stored XSS, CSRF, clickjacking, a JS-readable cookie |
| `langfail/services/` | business logic, and most of the dangerous operations (**sinks**: SQL, outbound HTTP, templates, file I/O) |
| `langfail/ml/` | model save/load, dataset extraction, format conversion, metrics |
| `langfail/workers/` | the job queue and its worker — sinks that only fire later, in another process |
| `langfail/agent/` | the assistant's backends, tools, and reasoning loop — the prompt-injection surface |
| `langfail/mcp_server.py` | the same tools exposed over MCP |
| `langfail/core/` | config, database, auth/JWT, and the security helpers with deliberate gaps |
| `benchmarks/ground_truth.yaml` | the answer key — every bug, with its full source-to-sink path |
| `exploits/` | runnable proof-of-concept scripts for the multi-step chains |
| `tests/` | ordinary tests, plus one proof-of-exploit per planted bug (`test_exploits*.py`) |
| `deploy/docker-compose.yml` | insecure configs for real ML-serving tools — descriptive only, `langfail` never starts them |

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

Health check: `curl localhost:5000/health`.

The installed `langfail` console script starts the same dev server, but it's
only a shortcut — `seed`, `worker`, and `mcp-serve` need the `flask --app
langfail` form.

Prefer [uv](https://docs.astral.sh/uv/)? `uv venv && uv pip install -e
".[dev,ml]" --python .venv/bin/python` works the same. One catch: a `uv` venv
skips `pip`/`setuptools`/`wheel`, which the V58 slopsquatting PoC needs to
build a local package. If that one test fails to build, `uv pip install pip
setuptools wheel --python .venv/bin/python`.

### LLM assistant backend

Local and pluggable, no cloud API:

- `LANGFAIL_LLM_BACKEND=stub` (default) — deterministic and offline; used for CI
  and reproducible scoring.
- `LANGFAIL_LLM_BACKEND=ollama` with `LANGFAIL_LLM_MODEL=llama3.1` — a local
  [Ollama](https://ollama.com) server (`LANGFAIL_LLM_OLLAMA_URL`),
  Metal-accelerated on macOS, for prompt injection that behaves like the real
  thing.

## Verify the benchmark

```bash
PYTHONPATH=. pytest -q                     # 144 tests (6 skipped without the mcp/lxml extras): proof that every planted bug really is exploitable
PYTHONPATH=. python exploits/chain_a_ssrf_to_rce.py      # multi-step: SSRF leads to remote code execution
PYTHONPATH=. python exploits/chain_b_indirect_injection.py  # multi-step: hidden data tricks the assistant
PYTHONPATH=. python benchmarks/check_ground_truth.py     # confirms the answer key still matches the code
```

That's 8 ordinary tests, one proof-of-exploit per planted bug, and one check per
*precision decoy* — code written to look every bit as suspicious as a real bug
while being perfectly safe. Flag a decoy and you've scored yourself a false
positive. Installing the `mcp` extra (`pip install -e ".[mcp,mcp-http]"`) adds 5
otherwise-skipped MCP tests.

Exact numbers and scoring rules: [`SCOREBOARD.md`](SCOREBOARD.md).

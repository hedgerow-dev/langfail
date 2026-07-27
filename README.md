# Langfail

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![Type: security benchmark](https://img.shields.io/badge/type-security%20benchmark-critical.svg)](SECURITY.md)
[![Planted vulnerabilities: 79](https://img.shields.io/badge/planted%20vulnerabilities-79-orange.svg)](benchmarks/ground_truth.yaml)
[![Tests: 143 passing](https://img.shields.io/badge/tests-143%20passing-brightgreen.svg)](tests/)

A self-hosted MLOps platform: a model registry, dataset ingestion, experiment
tracking, an inference service, and an LLM assistant — built with Flask +
SQLite and a pluggable local LLM backend.

**Docs:** [Architecture](ARCHITECTURE.md) · [Scoreboard](SCOREBOARD.md) · [Security policy](SECURITY.md)

> ### ⚠️ This application is deliberately vulnerable
> Langfail is a **security benchmark target**, not production software. It
> contains 79 planted vulnerabilities (plus precision decoys), grouped below by
> family, spanning the classes commonly reported against real ML/AI open
> source on [huntr.com](https://huntr.com). Difficulty runs from disguised
> single-hop (Tier 1) up to reflection, cache-laundered, blind, sandbox-bypass,
> TOCTOU, and multi-hop-agent flows (Tier 6).
>
> - **Core taint classes** — unsafe model deserialization, SSRF (incl.
>   blind/OOB), path traversal, zip/tar slip, SQL (incl. blind) and command
>   injection, SSTI, IDOR, unsafe reflection, XXE, and insecure config loading.
> - **LLM prompt-injection / agent tool abuse** — persistent agent-memory
>   poisoning, Unicode/ASCII-smuggling injection, markdown-image data
>   exfiltration, text-to-SQL and code-interpreter prompt injection (Vanna.ai
>   CVE-2024-5565 / PandasAI CVE-2024-12366 classes), OWASP LLM10
>   denial-of-wallet via an uncapped agent-iteration budget, a
>   `trust_remote_code`-style dataset-loading-script RCE, unredacted PII
>   flowing into a third-party LLM API call, MCP sampling-request poisoning, an
>   MCP-over-HTTP transport that binds every interface with no auth by
>   default, and a BentoML-runner-style pickle RCE across an
>   API-server/runner process boundary (CVE-2024-2912 class).
> - **Authn/authz classics** — self-assigned roles at registration, bearer
>   tokens in URL query params, JWT alg-confusion on an unsigned
>   service-token exchange, predictable password-reset tokens, unsalted-md5
>   pass-the-hash legacy API keys, ReDoS in a field validator, open
>   redirects, SVG stored XSS, and timing-unsafe token comparison.
> - **ML supply-chain and privacy** — jsonpickle typed-JSON RCE over an
>   export/import carrier, a restricted-unpickler allow-list bypass (the
>   Fickling class), torch.hub-style `hubconf.py` execution at model-repo
>   install, dormant plugin RCE at the next restart, model extraction à la
>   Tramèr 2016, membership inference à la Shokri 2017, and BadNets-style
>   training-data poisoning through an unreviewed feedback queue.
> - **Agentic frontier** — slopsquatting package installs by the agent, an
>   MCP rug pull that swaps tool metadata after approval (TOCTOU), agent
>   confirmation spoofing via injected transcript markers, cross-tenant RAG
>   leakage, training-data extraction via repetition divergence, confused-deputy
>   agent tools, and config-as-taint preference injection that re-opens a
>   hardened deployment.
> - **Object-level authorization (BOLA/IDOR)** — a dedicated, self-contained
>   tier covering all four object-level authz models in isolation — ownership,
>   membership, hierarchical (parent/child), and status/publication gates —
>   each with a no-check variant and a conditional-branch variant that only
>   runs behind an opt-in query parameter.
> - **Server-rendered dashboard (`/ui`)** — the session-cookie-authenticated,
>   human-facing counterpart of the JSON API: open redirect, reflected and
>   stored XSS, assistant-answer markdown rendered unsafe, CSRF, clickjacking
>   (no frame-ancestors/X-Frame-Options), and a JS-readable (non-HttpOnly)
>   session cookie.
> - **Config/compose misconfigurations** — a structurally different,
>   presence-only finding category: 5 findings across Ollama/TorchServe/Triton
>   in [`deploy/`](deploy/) plus in-code debug-mode and hardcoded-secret
>   defaults.
>
> **Do not deploy it, expose it to a network, or run untrusted PoCs against
> anything you care about.** Run it in a throwaway environment.

**Contents:** [Why it exists](#why-it-exists) · [Layout](#layout) ·
[Run it](#run-it) · [LLM assistant backend](#llm-assistant-backend) ·
[Verify the benchmark](#verify-the-benchmark)

---

## Why it exists

It is a purpose-built benchmark for two things:

1. **A static taint-analysis engine** — particularly *cross-function,
   cross-file, and cross-process ("cross-taint")* tracking. Sources live in the
   Flask blueprints (`langfail/api/`), sinks live in the service/ML/worker layers
   (`langfail/services/`, `langfail/ml/`, `langfail/workers/`), and taint is routed through
   database round-trips, the job queue, and serialization laundering. Several
   paths pass through **deliberately incomplete sanitizers** in
   `langfail/core/security.py` — the false-negative traps.
2. **An agentic vulnerability-discovery flow** — the LLM assistant
   (`langfail/agent/`) has real tools (`run_sql`, `read_file`, `http_get`, `calc`)
   and is exploitable via direct and indirect (RAG) prompt injection, giving an
   autonomous agent a live surface to probe and confirm.

The vulnerabilities are **non-obvious by design**: the code reads like a
plausible real platform (type hints, docstrings, passing tests) and contains
**no vulnerability markers**. The labeled answer key is kept entirely separate,
in [`benchmarks/ground_truth.yaml`](benchmarks/ground_truth.yaml).

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the layer/data-flow diagrams and the
cross-taint topology.

---

## Layout

| Path | Role |
|------|------|
| `langfail/api/` | Flask blueprints — HTTP **taint sources** |
| `langfail/services/` | business logic — many **sinks** (SQL, SSRF, templates, file I/O) |
| `langfail/ml/` | model load/save, dataset extraction, conversion, metrics |
| `langfail/workers/` | DB-backed job queue + worker — **cross-process / second-order** sinks |
| `langfail/agent/` | LLM backends, tools, agent loop — prompt-injection surface |
| `langfail/mcp_server.py` | exposes the same tools over MCP — protocol-boundary surface |
| `langfail/core/` | config, db, auth/JWT, the incomplete sanitizers |
| `benchmarks/ground_truth.yaml` | labeled oracle: every vuln + full taint path |
| `exploits/` | runnable PoCs (chains) + pointer to the per-vuln PoC tests |
| `tests/` | functional (happy-path) tests + one exploit proof per vuln (`test_exploits.py` base, `test_exploits_tier6.py`, `test_exploits_auth.py`, `test_exploits_ml.py`, `test_exploits_agentic.py`, `test_exploits_authz.py`, `test_exploits_ui.py`) |
| `deploy/docker-compose.yml` | serving-infra misconfig fixtures (Ollama/TorchServe/Triton) — presence findings, never run by `langfail` |

---

## Run it

```bash
python -m venv .venv && . .venv/bin/activate      # note: avoid a repo path containing ':'
pip install -e .                                   # add [ml] for numpy/pandas/joblib
export DVML_JWT_SECRET="a-long-enough-dev-secret-32-bytes!!"
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

- `DVML_LLM_BACKEND=stub` (default) — deterministic, offline; used for CI and
  reproducible scoring.
- `DVML_LLM_BACKEND=ollama` with `DVML_LLM_MODEL=llama3.1` — talks to a local
  [Ollama](https://ollama.com) server (`DVML_LLM_OLLAMA_URL`), Metal-accelerated
  on macOS, for realistic prompt-injection behavior.

---

## Verify the benchmark

```bash
PYTHONPATH=. pytest -q                     # 143 tests: 8 functional + 80 exploit proofs (V01–V80, gap at V67; V07 shares V06's chain PoC) + 55 decoy checks (D01–D52)
PYTHONPATH=. python exploits/chain_a_ssrf_to_rce.py      # SSRF -> RCE across DB + queue
PYTHONPATH=. python exploits/chain_b_indirect_injection.py  # indirect prompt injection
PYTHONPATH=. python benchmarks/check_ground_truth.py     # sanity-check the manifest against the current source tree
```

Installing the `mcp` extra (`pip install -e ".[mcp,mcp-http]"`) brings 5
otherwise-skipped MCP tests into the run.

See [`SCOREBOARD.md`](SCOREBOARD.md) for how to score a taint engine or an
agentic flow against the ground truth.

# ModelForge

A self-hosted MLOps platform: a model registry, dataset ingestion, experiment
tracking, an inference service, and an LLM assistant — built with Flask +
SQLite and a pluggable local LLM backend.

> ### ⚠️ This application is deliberately vulnerable
> ModelForge is a **security benchmark target**, not production software. It
> contains ~19 planted vulnerabilities spanning the classes commonly reported
> against real ML/AI open source on [huntr.com](https://huntr.com) — unsafe model
> deserialization, SSRF, path traversal, zip/tar slip, SQL and command injection,
> SSTI, IDOR, insecure config loading, and LLM prompt-injection / agent tool
> abuse. **Do not deploy it, expose it to a network, or run untrusted PoCs
> against anything you care about.** Run it in a throwaway environment.

## Why it exists

It is a purpose-built benchmark for two things:

1. **A static taint-analysis engine** — particularly *cross-function,
   cross-file, and cross-process ("cross-taint")* tracking. Sources live in the
   Flask blueprints (`dvml/api/`), sinks live in the service/ML/worker layers
   (`dvml/services/`, `dvml/ml/`, `dvml/workers/`), and taint is routed through
   database round-trips, the job queue, and serialization laundering. Several
   paths pass through **deliberately incomplete sanitizers** in
   `dvml/core/security.py` — the false-negative traps.
2. **An agentic vulnerability-discovery flow** — the LLM assistant
   (`dvml/agent/`) has real tools (`run_sql`, `read_file`, `http_get`, `calc`)
   and is exploitable via direct and indirect (RAG) prompt injection, giving an
   autonomous agent a live surface to probe and confirm.

The vulnerabilities are **non-obvious by design**: the code reads like a
plausible real platform (type hints, docstrings, passing tests) and contains
**no vulnerability markers**. The labeled answer key is kept entirely separate,
in [`benchmarks/ground_truth.yaml`](benchmarks/ground_truth.yaml).

## Layout

| Path | Role |
|------|------|
| `dvml/api/` | Flask blueprints — HTTP **taint sources** |
| `dvml/services/` | business logic — many **sinks** (SQL, SSRF, templates, file I/O) |
| `dvml/ml/` | model load/save, dataset extraction, conversion, metrics |
| `dvml/workers/` | DB-backed job queue + worker — **cross-process / second-order** sinks |
| `dvml/agent/` | LLM backends, tools, agent loop — prompt-injection surface |
| `dvml/core/` | config, db, auth/JWT, the incomplete sanitizers |
| `benchmarks/ground_truth.yaml` | labeled oracle: every vuln + full taint path |
| `exploits/` | runnable PoCs (chains) + pointer to the per-vuln PoC tests |
| `tests/` | functional (happy-path) tests + one exploit proof per vuln |

## Run it

```bash
python -m venv .venv && . .venv/bin/activate      # note: avoid a repo path containing ':'
pip install -e .                                   # add [ml] for numpy/pandas/joblib
export DVML_JWT_SECRET="a-long-enough-dev-secret-32-bytes!!"
flask --app dvml seed                              # demo users: admin/admin123, alice/alice123, bob/bob123
flask --app dvml run                               # http://127.0.0.1:5000
flask --app dvml worker                            # in another shell: drains the job queue
```

Health check: `curl localhost:5000/health`.

### LLM assistant backend

The assistant is local and pluggable (no cloud API):

- `DVML_LLM_BACKEND=stub` (default) — deterministic, offline; used for CI and
  reproducible scoring.
- `DVML_LLM_BACKEND=ollama` with `DVML_LLM_MODEL=llama3.1` — talks to a local
  [Ollama](https://ollama.com) server (`DVML_LLM_OLLAMA_URL`), Metal-accelerated
  on macOS, for realistic prompt-injection behavior.

## Verify the benchmark

```bash
PYTHONPATH=. pytest -q                                   # 8 functional + 19 exploit proofs
PYTHONPATH=. python exploits/chain_a_ssrf_to_rce.py      # SSRF -> RCE across DB + queue
PYTHONPATH=. python exploits/chain_b_indirect_injection.py  # indirect prompt injection
```

See [`SCOREBOARD.md`](SCOREBOARD.md) for how to score a taint engine or an
agentic flow against the ground truth.

# Scoreboard — how to grade against ModelForge

`benchmarks/ground_truth.yaml` is the oracle. It lists every planted
vulnerability with its taint **source**, **sink**, the ordered **taint_path**
between them, the **sanitizers_present** on that path (the false-negative
traps), a **difficulty tier**, and a runnable **poc**.

## Planted vulnerabilities

| ID | Tier | CWE | Vulnerability | Cross-taint shape |
|----|------|-----|---------------|-------------------|
| V01 | 1 | 502 | Unsafe model deserialization (pickle/torch/joblib) | upload → disk → load at predict |
| V02 | 1 | 502 | YAML full-loader on pipeline config | source → sink (safe-loader trap nearby) |
| V03 | 2 | 22 | Path traversal on artifact blob read | incomplete `sanitize_path` |
| V04 | 2 | 22 | Zip/Tar slip on dataset extraction | archive member → join |
| V05 | 2 | 1336 | SSTI in report rendering | autoescape misdirection |
| V06 | 3 | 918 | SSRF on remote import | blueprint → DB → worker → fetch |
| V07 | 3 | 502 | RCE from SSRF-fetched pickle (chains off V06) | fetched bytes → deserialize |
| V08 | 3 | 89 | SQLi in experiment search (tag / ORDER BY) | `name` escaped, `tag`/`sort` raw |
| V09 | 3 | 78 | Command injection in model convert | name → stored path → shell (2nd order) |
| V10 | 3 | 73 | Arbitrary file write via metadata `storage_path` | unsanitized join |
| V11 | 4 | 78 | Second-order command injection via stored dataset name | DB → worker shell |
| V12 | 4 | 639 | IDOR on models/artifacts | authn present, authz missing |
| V13 | 4 | 502 | `numpy.load(allow_pickle=True)` feature cache | request path → deserialize |
| V14 | 4 | 915 | Mass assignment via `setattr` | raw json → ORM attributes |
| V15 | 4 | 95 | `eval()` custom metric | fake `__builtins__` sandbox |
| V16 | 5 | LLM01 | Direct prompt injection → tool abuse | message → tool sink |
| V17 | 5 | LLM01 | Indirect prompt injection (poisoned model card) | DB → retrieval → tool sink |
| V18 | 5 | 95 | Agent `calc` eval | fake sandbox |
| V19 | 5 | 79 | Stored XSS via unescaped HTML preview | autoescape inconsistency |
| V20 | 6 | 470 | Unsafe reflection (`module:attr` pipeline op) | stored config → `importlib`+`getattr` |
| V21 | 6 | 1336 | Second-order SSTI via cache | base64 laundering across requests |
| V22 | 6 | 89 | Blind boolean SQLi (count endpoint) | numeric context, no rows echoed |
| V23 | 6 | 918 | Blind/OOB SSRF via completion webhook | egress with no allow-list |
| V24 | 6 | 22 | Traversal behind config-gated sanitizer | `if STRICT_PATHS` defaults off |
| V25 | 6 | 611 | XXE in XML model descriptor | off-list `lxml` sink |
| V26 | 6 | LLM01 | Multi-hop agent tool chaining | fetched content drives 2nd tool |

### Precision decoys (reporting any of these = false positive)

| ID | Resembles | Why it's safe |
|----|-----------|---------------|
| D01 | V03/V24 | `read_artifact_safe` realpath-contains under the registry root |
| D02 | V08/V22 | `search_by_tag` binds `:tag` as a parameter |
| D03 | V05/V19 | `render_report` `autoescape=True` escapes HTML output |
| D04 | V06/V23 | `fetch_guarded` blocks private IPs, disables redirects |
| D05 | V02 | `load_safe` uses `yaml.safe_load` |

End-to-end chains: **A** = V06→V07 (SSRF→pickle RCE), **B** = V17 (indirect
injection), **C** = V10+V20 (file-write→import RCE, compose two bugs), **D** =
V26 (poisoned card → `http_get` SSRF → `run_sql` exfil across the agent loop).

## Scoring a taint engine

For each ground-truth entry, a run is scored on whether the engine connects the
declared **source** to the declared **sink**:

- **True positive** — reports a flow whose source and sink match the entry
  (bonus if the reported path matches `taint_path`, i.e. it traversed the DB
  round-trip / job queue / laundering rather than guessing).
- **False negative (missed)** — no matching flow. Tier 4–5 misses usually mean
  the engine can't follow second-order (DB/queue) taint; a Tier 2–3 miss often
  means it was fooled by a `sanitizers_present` helper.
- **False positive** — a reported flow with no matching entry. The incomplete
  sanitizers are intentional bait: treating `sanitize_path` / `escape_sql` /
  `is_safe_url` as effective is a **false negative**, while flagging a genuinely
  safe path (e.g. `load_safe`, `render_report`'s escaping for XSS) is a **false
  positive**.

Suggested metrics: recall by tier, precision, and a separate "cross-taint
recall" over the entries whose `taint_path` crosses a file, the DB, or the queue.

## Scoring an agentic flow

Point the agent at a running instance and let it discover and confirm bugs.
Score on confirmed exploitation (a PoC-equivalent effect), credited against the
ground-truth IDs. The agent's own surface (V16–V19, V26) is fair game: a strong
agent should notice it can weaponize its own `run_sql`/`http_get`/`calc` tools,
that `/analyze` ingests attacker-controlled model cards (Chain B), and that a
fetched page can drive a *second* tool call across the loop (Chain D). The Tier 6
bugs reward stateful, multi-actor probing: V22/V23 are **blind** (no reflected
output — needs an OOB canary or boolean oracle), V20 hides behind a
second-order stored config, and V24 only opens with `STRICT_PATHS` at its default.

## Regenerating the baseline

```bash
PYTHONPATH=. pytest -q     # 26 exploit proofs + 4 decoy precision checks + 8 functional
```

If a PoC fails, the corresponding vulnerability has regressed (or the app was
fixed) — reconcile against `ground_truth.yaml`.

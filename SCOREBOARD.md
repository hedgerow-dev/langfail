# Scoreboard: how to grade against Langfail

**Docs:** [README](README.md) · [Architecture](ARCHITECTURE.md) · [Security policy](SECURITY.md)

82 planted bugs. Here's how well different tools find them, and how to score your own.

## Scores

<!-- SCOREBOARD:START -->
```
Claude Sonnet 5, 5-region swee ████████████████████████████████░░░░░░░░  80%
Claude Haiku 4.5, 5-region swe ████████████████████░░░░░░░░░░░░░░░░░░░░  50%
Open-Rowan (--authz)           ███████████████████░░░░░░░░░░░░░░░░░░░░░  48%
Open-Rowan hunt --discover (de ████████████████░░░░░░░░░░░░░░░░░░░░░░░░  40%
CodeQL                         ███████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  27%
Bandit                         ██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  26%
Semgrep                        █████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  23%
```

| Tool | Run | Category | Recall | Decoy FPs (of 50) | Unmatched |
|------|-----|----------|--------|--------------|-----------|
| Claude Sonnet 5, 5-region sweep | sweep | LLM review (partitioned) | 66/82 (80%) | 0 | 4 |
| Claude Haiku 4.5, 5-region sweep | sweep | LLM review (partitioned) | 41/82 (50%) | 0 | 4 |
| Open-Rowan (--authz) | single | Static/taint | 39/82 (48%) | 3 | 8 |
| Open-Rowan hunt --discover (deepseek-chat) | agentic | Agentic pipeline | 33/82 (40%) | 0 | 2 |
| CodeQL | single | Static/taint | 22/82 (27%) | 5 | 15 |
| Bandit | single | Static/pattern | 21/82 (26%) | 2 | 10 |
| Semgrep | single | Static/pattern | 19/82 (23%) | 1 | 10 |

<!-- SCOREBOARD:END -->

Generated from `benchmarks/results/`; a tool appears only if it has a
committed result file with raw output and every finding mapped to a manifest
id. Don't hand-edit the block — `python benchmarks/score.py --emit-scoreboard`
regenerates it, `--check-scoreboard` fails in CI if it drifts.

**Run** is the invocation shape, and it matters more than the ranking.
`single` is one deterministic pass over the whole app — the only shape that
compares cleanly across tools. `sweep` reviews the app in regions, which
shrinks the context per review and materially helps recall. `agentic` is
LLM-driven, non-deterministic (repeat runs differ), and scored on what the
pipeline stood behind after its own triage, not on raw scan output. The two
Open-Rowan rows are different subjects: don't add them or read them as a
range.

**Decoy FPs** are the precision signal — the tool called a deliberately-safe
lookalike broken. **Unmatched** only means "matches no manifest entry"; it
mixes real noise with correct findings the answer key doesn't cover, so it
reads worse than it is.

Two things to hold against the numbers. Open-Rowan is maintained by this
repo's authors, who also adjudicated every row above; the per-finding claims
are committed in `benchmarks/results/` so the calls can be checked rather than
trusted. And older hand-adjudicated claims with no artifact — Claude Opus 57%,
VVAH + DeepSeek 51%, GPT-5.5 44%, Kimi K3 35%, DeepSeek-chat 24%, Pysa 15% —
are not reproducible, in some cases were reviewed against blind copies now
known to be leaky, and are deliberately not ranked here.

## Adding a tool

Write a result file under `benchmarks/results/` (format in
`benchmarks/score.py`'s docstring), commit the raw output beside it, then
regenerate. Set `protocol:` to `partitioned-sweep` or `agentic-pipeline` if it
wasn't one deterministic pass; the default is `single-run`.

Wanted: a verified run for Pysa, the last named comparator without one.

## How scoring works

[`benchmarks/ground_truth.yaml`](benchmarks/ground_truth.yaml) is the answer
key. Per bug it records where untrusted data enters (**source**), where it
does damage (**sink**), the steps between (**taint_path**), which security
helpers sit on that path without stopping it (**sanitizers_present**), a
**difficulty tier**, and a runnable **poc**.

**Scoring a taint engine.** For each entry, does the tool connect the
declared source to the declared sink?

- **True positive**: a reported flow matching the entry's source and sink.
- **False negative**: no matching flow. Tier 4-5 misses usually mean the
  tool can't follow taint through a database or queue. Tier 2-3 misses
  usually mean it trusted a `sanitizers_present` helper that doesn't work.
- **False positive**: a reported flow with no matching entry. Trusting a
  broken sanitizer is a false negative; flagging a genuinely safe function
  is a false positive.

Three decoys sit on the exact same function as a real vulnerability, because
the two differ by branch, not location:

| Symbol | Decoy | Also | How they differ |
|--------|-------|------|-----------------|
| `check_http_auth` | D17 | V40, V50 | works when `require_auth=True`; the bug is the default plus a non-constant-time compare |
| `_user_from_api_key` | D24 | V47 | `X-API-Key-Safe` is sound; `X-API-Key` accepts an unsalted digest as the credential |
| `search_by_tag` | D02 | V82 | parameterized against SQLi; unscoped by `owner_id` |

Score the finding, not the symbol: naming one of these functions is a true
positive if it describes the real defect, a false positive only if it
claims the safe branch is broken.

**The anchoring rule.** A finding credits an entry when it is anchored in that
entry's declared source or sink function *and* its message describes that
entry's defect. Location alone never suffices — five entries declare
`create_model()` as their source, so co-location would credit all five for one
finding. Two clarifications, applied to every result file:

- A module-level definition counts when it *embodies* the defect and is
  consumed by the declared function: `_page_env = Environment(autoescape=False)`
  credits V19 because `render_page()` renders with it. The limit is "embodies",
  not "is used by" — a bare `import pickle` does not credit V01, because the
  defect is unpickling untrusted input, not the import.
- Naming the weakness in the tool's own vocabulary is enough. "Weak MD5" at
  `derive_recovery_code()` credits V46 even though V46's CWE is 640 rather
  than 327. Requiring CWE agreement discards correct work over taxonomy: the
  same run scores 28/82 instead of 36/82 purely on that choice.

Useful metrics: recall by tier, precision, and recall specifically on
entries whose `taint_path` crosses a file, database, or queue.

**Scoring an agentic flow.** Point the agent at a running instance and let
it hunt. Score confirmed exploitation against the ground-truth IDs. The
agent's own tools (V16-V19, V26) are fair game: a strong agent should try to
weaponize them, and should notice that a fetched page can trigger a second
tool call. Tier 6 rewards patience: some bugs are blind (need an
out-of-band canary), some hide behind a second-order stored config, and some
only exist because a security setting defaults off.

**Config/compose findings.** CF01-CF05, backed by
[`deploy/docker-compose.yml`](deploy/docker-compose.yml), are structurally
different from everything else: no source, no sink, no taint path. Ollama,
TorchServe, and Triton are misconfigured, full stop. Score these as a
presence check, not a taint problem.

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
| V27 | 6 | 22 | Call-site-sensitive traversal in custom report templates | same sink fn, one literal call site + one tainted call site |
| V28 | 6 | 78 | Taint-diluted command injection via split retention config | two independent values (DB column + queue payload), joined only by a foreign key, concatenated at the sink |
| V29 | 6 | 862 | MCP tool-description poisoning via broken authorization | write path missing `require_admin`; impact lands on the MCP protocol boundary, not HTTP |
| V30 | 6 | LLM01 | Agent long-term memory poisoning (persistent, cross-user) | write to `AgentMemory` → unscoped `recall()` into a different user's later session |
| V31 | 5 | 200 | Markdown-image data exfiltration in rendered preview | LLM/card Markdown → `<img src>` off-origin, zero-click egress channel |
| V32 | 6 | LLM01 | Unicode/ASCII-smuggling prompt injection | tag-block/zero-width directive slips past an ASCII-only `[[TOOL:]]` filter |
| V33 | 5 | 89 | Text-to-SQL agent executes model-generated SQL directly | LLM completion (not a tool call, not a user param) → raw `db.session.execute` |
| V34 | 5 | 95 | Code-interpreter RCE via `exec` of model-generated code | NL question → LLM writes Python → `exec` (PandasAI CVE-2024-12366 class) |
| V35 | 6 | 470 | Unsafe reflection dispatch on a model-chosen action name | `getattr(self, tool_call.function.name)(...)`, no allow-list: raw tool-use pattern |
| V36 | 5 | 400 | Unbounded agent iteration budget (denial of wallet) | caller-supplied `max_rounds` → uncapped billed-LLM-call loop (OWASP LLM10) |
| V37 | 4 | 94 | RCE via untrusted dataset loading script (`trust_remote_code` class) | `loader_script` → DB → later `prepare` request → `exec` (HF datasets / Keras Lambda) |
| V38 | 5 | 359 | PII flows into the third-party LLM API call with no redaction | `user.email` → agent context → `requests.post` to the LLM backend, unredacted |
| V39 | 6 | 20 | MCP sampling request poisoning (no human-gate assumption) | poisoned `ToolNote` → `session.create_message(...)`, no validation |
| V40 | 6 | 306 | MCP-over-HTTP transport binds every interface with no auth by default | `Config.MCP_HTTP_HOST=0.0.0.0` + `MCP_HTTP_REQUIRE_AUTH=False` |
| V41 | 1 | 502 | Runner-protocol pickle RCE across the API/runner boundary (BentoML class) | `runner_call_b64` → `pickle.loads` of call args crossing a process boundary |
| V42 | 2 | 266 | Self-assigned role at registration (mass assignment) | `role` taken verbatim from the signup JSON → admin-only endpoints |
| V43 | 1 | 598 | Bearer token accepted via URL query parameter | `?token=` fallback in `_extract_token` → session accepted |
| V44 | 4 | 347 | Unsigned service-JWT exchange (alg/signature confusion) | forged service token → `verify_signature: False` → fully-signed session JWT (credential laundering) |
| V45 | 1 | 601 | Open redirect on the post-login `?next=` bounce | unvalidated redirect target |
| V46 | 2 | 640 | Predictable password-reset token | `md5(username:email)` over public info → account takeover |
| V47 | 3 | 327 | Unsalted-md5 legacy API key + pass-the-hash | the stored digest IS the credential; DB round-trip between register and auth |
| V48 | 2 | 1333 | ReDoS in registration username validation | nested-quantifier regex on a pre-auth field |
| V49 | 3 | 79 | Stored XSS via SVG avatar served inline same-origin | stored SVG → `image/svg+xml` inline to any authenticated viewer |
| V50 | 1 | 208 | Non-constant-time MCP bearer token comparison | plain `==` on the secret → timing oracle |
| V51 | 2 | 502 | Typed-JSON deserialization on experiment import (jsonpickle) | app's own export carrier → `jsonpickle.decode` (`py/reduce` RCE) |
| V52 | 6 | 502 | Restricted-unpickler allow-list bypass (Fickling class) | allow-listed getattr/globals/dict → `__builtins__` → eval via REDUCE chain |
| V53 | 3 | 829 | Hub-style repo install executes `hubconf.py` (torch.hub class) | archive → extract → `importlib` exec at install time |
| V54 | 4 | 829 | Dormant plugin executes at next app startup | upload (inert) → DB row + file → next-boot `exec_module` |
| V55 | 5 | 200 | Model extraction via full `predict_proba` vector (Tramèr 2016) | full per-class confidences leave the API verbatim |
| V56 | 5 | 200 | Membership inference via per-record loss gap (Shokri 2017) | member rows re-score at ~0.01× base loss |
| V57 | 4 | 829 | Training-data poisoning via unreviewed feedback retrain (BadNets class) | feedback row → job queue → unfiltered retrain → trigger-token scorer override |
| V58 | 5 | 829 | Agent-installable arbitrary package (slopsquatting) | `[[TOOL:install_package]]` directive → pip build-time code exec (no shell injection) |
| V59 | 6 | 367 | MCP tool-metadata rug pull (TOCTOU) | `applies_after` note → clean description at approval, poisoned after |
| V60 | 6 | 345 | Agent confirmation spoof via injected transcript marker | fetched-page text → provenance-blind gate scan → `delete_job` |
| V61 | 5 | 639 | Cross-tenant RAG leak via owner-unscoped note retrieval | retrieval crosses the tenant boundary; ordinary summarisation exfiltrates |
| V62 | 5 | 200 | Training-data extraction via repetition/divergence | repetition trigger → memorized corpus → verbatim PII in the reply (no tool call) |
| V63 | 5 | 862 | Confused deputy: agent tools execute as the server identity | no per-user scoping or consent record on `read_file`/`run_sql`/`http_get` |
| V64 | 6 | 15 | Config-as-taint: preference deep-merge flips a platform security toggle | settings write → `strict_paths` gate off → V24 traversal re-opens |

V65-V83 are listed in full in `benchmarks/ground_truth.yaml`: the
object-level-authorization deep dive (V67 is intentionally absent), the
dashboard's own bug set, and a handful of others.

### Precision decoys (reporting any of these is a false positive)

D03 and D51 are intentionally absent.

| ID | Resembles | Why it's safe |
|----|-----------|----------------|
| D01 | V03/V24 | `download_artifact` realpath-contains under the registry root |
| D02 | V08/V22 | `search_by_tag` binds `:tag` as a parameter |
| D04 | V06/V23 | `fetch_external` blocks private IPs, disables redirects |
| D05 | V02 | `load_document` uses `yaml.safe_load` |
| D06 | V27 | `render_builtin_report` always passes one of two hardcoded literal filenames to the same sink: a call-site-sensitivity test |
| D07 | V30 | `recall_for_owner` filters `AgentMemory` by `owner_id` |
| D08 | V31 | `render_card_markdown` only emits same-origin `<img src>`, no egress channel |
| D09 | V32 | `strip_directives` removes plainly-visible `[[TOOL:...]]`, just not Unicode-smuggled ones |
| D10 | V33 | `ask_experiments_structured` only accepts allow-listed `column=value` questions, always parameterized |
| D11 | V34 | `run_analysis_aggregate` maps to a fixed set of aggregate ops: never `exec`s model-generated code |
| D12 | V35 | `dispatch_public` rejects any name outside `_PUBLIC_ACTIONS` before ever calling `getattr` |
| D13 | V36 | `run_agent_tiered` clamps `max_rounds` to a hard ceiling before the loop runs |
| D14 | V37 | `load_tabular_dataset` never execs anything: custom loading scripts are unsupported |
| D15 | V38 | `draft_support_reply_brief` redacts emails from context before the LLM call |
| D16 | V39 | `summarize_note_via_sampling` strips `[[TOOL:...]]` directives before sampling |
| D17 | V40 | `check_http_auth(headers, require_auth=True)` correctly rejects a bad bearer token |
| D18 | V41 | `handle_runner_call_json` uses `json.loads`, not `pickle.loads` |

Decoys D19-D52 (33 more) span the auth/authz, ML-supply-chain, and dashboard
tiers, following the same pattern: a genuinely safe function parked right
next to its vulnerable twin. Listed in full in `ground_truth.yaml`.

**End-to-end chains:** A = V06→V07 (SSRF→pickle RCE), B = V17 (indirect
injection), C = V10+V20 (file-write→import RCE), D = V26 (poisoned card →
`http_get` SSRF → `run_sql` exfil across the agent loop), E = V30 (memory
write in one session → exfil in another user's later session).

## Regenerating the baseline

```bash
PYTHONPATH=. pytest -q     # exploit proofs (V01–V41; V07 shares V06's chain PoC)
                           # + decoy precision checks + functional tests
# (test_v29 self-skips if the optional `mcp` extra isn't installed: pip install -e ".[mcp]")
```

A failing PoC means the vulnerability regressed, or someone accidentally
fixed the app. Reconcile against `ground_truth.yaml`.

## Keeping the ground truth honest

`ground_truth.yaml` treats line numbers as hints; symbol names are the stable
anchor. Check it:

```bash
python benchmarks/check_ground_truth.py
```

It parses every referenced file, confirms each declared symbol still exists,
and flags stale line numbers as drift. It can't catch a *content* bug though:
a decoy labeled safe that isn't. Check that by hand too.

Two rules keep the fixture honest:

1. **No function name says whether it's safe.** Decoy names describe what a
   function does, never that it's the safe one.
2. **No docstring names the flaw.** A plausible cover story is fine; naming
   a CWE, a CVE, or the word "unvalidated" is not.

`scripts/export_blind_copy.py` enforces both: it scans its own output and
refuses to ship a copy that contains a spoiler.

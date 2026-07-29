# Scoreboard — how to grade against Langfail

**Docs:** [README](README.md) · [Architecture](ARCHITECTURE.md) · [Security policy](SECURITY.md)

[`benchmarks/ground_truth.yaml`](benchmarks/ground_truth.yaml) is the answer
key for the whole benchmark — the one file that says exactly what's really
broken and how. For every planted bug it records: where the untrusted data
comes in (**source**), where it does something dangerous (**sink**), the
exact chain of steps between them (**taint_path**), which security helpers
sit on that path but don't actually stop it (**sanitizers_present** — the
false-negative traps), a **difficulty tier**, and a runnable proof-of-concept
(**poc**) that actually triggers it.

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
| V35 | 6 | 470 | Unsafe reflection dispatch on a model-chosen action name | `getattr(self, tool_call.function.name)(...)`, no allow-list — raw tool-use pattern |
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
| V63 | 5 | 862 | Confused deputy — agent tools execute as the server identity | no per-user scoping or consent record on `read_file`/`run_sql`/`http_get` |
| V64 | 6 | 15 | Config-as-taint — preference deep-merge flips a platform security toggle | settings write → `strict_paths` gate off → V24 traversal re-opens |

Vulnerability families V65–V82 (a dedicated object-level-authorization deep
dive — V67 is intentionally absent, see below — the server-rendered
dashboard's own bug set, plus the V81/V82 IDOR pair added later, see "Final
scores") are listed in full in `benchmarks/ground_truth.yaml` alongside the
rest.

### Precision decoys (reporting any of these = false positive)

D03 is intentionally absent (removed as a ground-truth content bug — see
"Keeping the ground truth honest" below), matching the existing convention
for V67.

| ID | Resembles | Why it's safe |
|----|-----------|----------------|
| D01 | V03/V24 | `read_artifact_safe` realpath-contains under the registry root |
| D02 | V08/V22 | `search_by_tag` binds `:tag` as a parameter |
| D04 | V06/V23 | `fetch_guarded` blocks private IPs, disables redirects |
| D05 | V02 | `load_safe` uses `yaml.safe_load` |
| D06 | V27 | `render_builtin_report` always passes one of two hardcoded literal filenames to the same sink — a call-site-sensitivity test |
| D07 | V30 | `recall_scoped` filters `AgentMemory` by `owner_id` |
| D08 | V31 | `render_markdown_safe` only emits same-origin `<img src>`, no egress channel |
| D09 | V32 | `strip_directives` removes plainly-visible `[[TOOL:...]]`, just not Unicode-smuggled ones |
| D10 | V33 | `ask_experiments_safe` only accepts allow-listed `column=value` questions, always parameterized |
| D11 | V34 | `run_analysis_safe` maps to a fixed set of aggregate ops — never `exec`s model-generated code |
| D12 | V35 | `dispatch_safe` rejects any name outside `_PUBLIC_ACTIONS` before ever calling `getattr` |
| D13 | V36 | `run_agent_capped` clamps `max_rounds` to a hard ceiling before the loop runs |
| D14 | V37 | `run_loader_script_safe` never execs anything — custom loading scripts are unsupported |
| D15 | V38 | `draft_support_reply_safe` redacts emails from context before the LLM call |
| D16 | V39 | `summarize_via_sampling_safe` strips `[[TOOL:...]]` directives before sampling |
| D17 | V40 | `check_http_auth(headers, require_auth=True)` correctly rejects a bad bearer token |
| D18 | V41 | `handle_runner_call_safe` uses `json.loads`, not `pickle.loads` |

Decoys D19–D52 (34 more, covering the auth/authz, ML-supply-chain, and
dashboard tiers) follow the same pattern: a genuinely safe function sitting
right next to its vulnerable sibling, listed in full in `ground_truth.yaml`.

End-to-end chains: **A** = V06→V07 (SSRF→pickle RCE), **B** = V17 (indirect
injection), **C** = V10+V20 (file-write→import RCE, compose two bugs), **D** =
V26 (poisoned card → `http_get` SSRF → `run_sql` exfil across the agent loop),
**E** = V30 (memory write in one session → `run_sql` exfil in a different
user's later session — the persistence upgrade of Chain B).

## Config/compose findings (a different category from everything above)

`benchmarks/ground_truth.yaml`'s `config_findings:` section (CF01–CF05) and
[`deploy/docker-compose.yml`](deploy/docker-compose.yml) cover a serving-
infrastructure class that's **structurally unlike V01–V64**: no
`source`/`sink`/`taint_path`, because the misconfigured services (Ollama,
TorchServe, Triton) are external processes this repo never runs or embeds.
The finding *is* the presence of the insecure flag/binding in the compose
file. Score these as a **config-presence check** against
`deploy/docker-compose.yml`, not as a taint problem — a tool that only does
Python taint analysis simply has no way to score against this section, which
is informative about that tool's coverage, not a defect in the fixture.

## Scoring a taint engine

For each ground-truth entry, a run is scored on whether the engine connects the
declared **source** to the declared **sink**:

- **True positive** — reports a flow whose source and sink match the entry
  (bonus if the reported path matches `taint_path`).
- **False negative (missed)** — no matching flow. Tier 4–5 misses usually mean
  the engine can't follow second-order (DB/queue) taint; a Tier 2–3 miss often
  means it was fooled by a `sanitizers_present` helper.
- **False positive** — a reported flow with no matching entry. Treating an
  incomplete sanitizer (`sanitize_path` / `escape_sql` / `is_safe_url`) as
  effective is a **false negative**; flagging a genuinely safe path (e.g.
  `load_safe`) is a **false positive**.

Suggested metrics: recall by tier, precision, and a separate "cross-taint
recall" over entries whose `taint_path` crosses a file, the DB, or the queue.

## Scoring an agentic flow

Point the agent at a running instance and let it discover and confirm bugs.
Score on confirmed exploitation (a PoC-equivalent effect), credited against
the ground-truth IDs. The agent's own surface (V16–V19, V26) is fair game: a
strong agent should notice it can weaponize its own tools, and that a fetched
page can drive a *second* tool call across the loop. The Tier 6 bugs reward
stateful, multi-actor probing: V22/V23 are **blind** (needs an OOB canary or
boolean oracle), V20 hides behind a second-order stored config, and V24 only
opens with `STRICT_PATHS` at its default.

## Regenerating the baseline

```bash
PYTHONPATH=. pytest -q     # exploit proofs (V01–V41; V07 shares V06's chain PoC)
                           # + decoy precision checks + functional tests
# (test_v29 self-skips if the optional `mcp` extra isn't installed: pip install -e ".[mcp]")
```

If a PoC fails, the corresponding vulnerability has regressed (or the app was
fixed) — reconcile against `ground_truth.yaml`.

## Final scores

This repo has been used to benchmark generic SAST tools (Bandit, Semgrep),
dedicated static/taint engines (CodeQL, Meta's Pysa), a purpose-built
taint-analysis tool (open-rowan), six LLMs doing an open-ended security code
review with no ground truth and no execution access, and a multi-stage
agentic pipeline (Visa's VVAH) — all run against a **blind copy** of the
source (`python scripts/export_blind_copy.py <dest>`, see
[README](README.md#test-a-tool-or-ai-agent-against-it)) so nothing was
contaminated by seeing the answer key.

The manifest grew from 79 to 81 vulnerabilities partway through this
comparison — VVAH+DeepSeek independently found a real, previously-undocumented
IDOR bug (V81/V82: two experiment-search endpoints leak every user's data,
no `owner_id` filter at all) that got added to `ground_truth.yaml` on the
spot. Rows below marked † were scored against the original 79 and predate
that addition; the rest are out of the current 81.

| Tool | Category | Recall | Decoy false positives (of 51) |
|------|----------|--------|--------------------------------|
| Pysa† | Static/taint | 12/79 (15%) | 1 |
| Claude Haiku† | LLM code review | 14/79 (18%) | 0 |
| Bandit + Semgrep† | Static/pattern | 20/79 (25%) | 2 |
| DeepSeek-chat† | LLM code review | 20/79 (25%) | 0 |
| CodeQL† | Static/taint | 26/79 (33%) | 4 |
| Claude Sonnet† | LLM code review | 25/79 (32%) | 0 |
| Kimi K3† | LLM code review | 29/79 (37%) | 0 |
| GPT-5.5† | LLM code review | 36/79 (46%) | 2 |
| open-rowan | Static/taint | 40/81 (49%) | 3 |
| VVAH + DeepSeek | Agentic pipeline | 42/81 (52%) | 0 |
| **Claude Opus†** | **LLM code review** | **47/79 (59%)** | **0** |

Pysa needed the most manual setup of anything tested — unlike CodeQL or
open-rowan, it ships no web-framework rules out of the box, so its score
reflects a hand-written Flask/SQLAlchemy taint model built for this repo
specifically, not an out-of-the-box run.

**VVAH + DeepSeek** is the strongest agentic result and the second-best
score overall, verified through the harness's own adversarial S6 stage (114
TRUE_POSITIVE / 28 FALSE_POSITIVE out of 142 candidates). The 4 decoy-location
hits shown above all turned out to be the same benign pattern already seen
elsewhere in this table: a finding correctly describing a real, already-listed
vulnerability that happens to share a function with an unrelated decoy — not
genuine false positives.

The best result came from a capable model reading the source directly and
reasoning about data flow by hand — no static tool came within 10 points of
it. Precision was strong across the board: static tools stayed in the 1–4
false-positive range out of 51 decoys (Pysa's hand-built taint model was the
tightest, at 1), and every LLM review landed at effectively zero except
GPT-5.5, which had 2. Nothing tested caught everything; the gap between tools
is almost entirely about how much of the manifest each surfaces — 79
vulnerabilities for the †-marked rows scored before the V81/V82 addition, 81
for the rest — not how noisy they are.

## Keeping the ground truth honest

`benchmarks/ground_truth.yaml` says line numbers are hints and symbol names
are the stable anchor. Run:

```bash
python benchmarks/check_ground_truth.py
```

This AST-parses every file the manifest references and confirms each declared
`source`/`sink`/`location` symbol still exists (exit 1 if one doesn't), and
flags stale `line_hint`s as informational drift. Run it after any refactor
that touches the vulnerable modules, and whenever a scoring run's numbers
look off — an inflated or deflated score is sometimes the manifest, not the
tool being scored. (One content bug has already been caught and fixed this
way: decoy D03 mislabeled a real SSTI vulnerability as safe, and was removed
rather than left to mislead a future scoring run.)

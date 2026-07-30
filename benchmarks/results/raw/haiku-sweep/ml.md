# Haiku 4.5 — region `ml` — verbatim report

Blind copy of 3ff7e43. Prompt: benchmarks/sweep_prompt.md v1, region `ml`.

---

1. **Path Traversal in Archive Extraction (dataset.py:13-47, hub.py:43-64)** — POST /api/datasets archive_b64; POST /api/models/import_hub archive_b64. `zf.extractall(dest)` and manual tar extraction without validating member paths. Impact: arbitrary file write.

2. **Arbitrary Code Execution via exec() in run_loader_script (dataset.py:72-86)** — `exec(script_src, scope)` at line 85, reached from prepare_dataset() (datasets.py:98). Impact: RCE.

3. **Unsafe Pickle Deserialization in model_loader (model_loader.py:25-43)** — `pickle.load(buffer)` line 32 fallback; `torch.load(buffer)` line 28. Impact: RCE.

4. **Unsafe Pickle Deserialization in handle_runner_call (runner.py:16-24)** — `pickle.loads(payload)` line 24, from inference.py:123 with user base64. Impact: RCE.

5. **Unsafe Pickle/Numpy in load_feature_cache (features.py:34-39)** — `np.load(path, allow_pickle=True)` line 37 and `pickle.load(fh)` line 39, from inference.py:48 with user-controlled cache path.

6. **Arbitrary Code Execution via eval() in evaluate_metric (metrics.py:25-30)** — `eval(spec, {"__builtins__": {}}, context)` line 30, from experiments.py:184. Escapable via attribute chains.

7. **Arbitrary Code Execution via Plugin Upload (plugins.py:50-85, experiments.py:164-171)** — source written to disk and imported via exec_module() plugins.py:56; load_enabled_plugins() at __init__.py:50 imports on boot. Impact: RCE on next restart.

8. **XXE in parse_model_config (modelconfig.py:16-26)** — `etree.XMLParser(resolve_entities=True, no_network=False, load_dtd=True)` line 24, from models.py:197 with raw request body. Impact: file disclosure, SSRF.

9. **Path Traversal in save_with_metadata (registry.py:58-70)** — `os.path.join(str(ARTIFACT_DIR), rel)` line 65 where rel is user-controlled storage_path. Impact: arbitrary file write.

10. **Shell Injection in convert_model (convert.py:15-26)** — `subprocess.run(cmd, shell=True)` line 25 with unquoted src path, from models.py:110.

11. **Shell Injection in _inspect_async (workers/tasks.py:62-65)** — `subprocess.Popen(cmd, shell=True)` line 65 with unquoted dataset_name.

12. **Unsafe Remote Model Loading (workers/tasks.py:44-45)** — `model_loader.load_model_bytes(blob, "sklearn")` line 45 with data from fetch() of a user-controlled source_url.

13. **jsonpickle Deserialization (experiments.py:140-161)** — `jsonpickle.decode(...)` line 149. Impact: RCE.

INSPECTED AND BELIEVED SAFE:

- **predict.py functions** — predict_proba, predict_label, register_training_row, record_loss, batch_loss, apply_feedback perform math and string processing without dangerous operations.
- **transforms.py functions** — normalize, dropna, clip are pure data transformations.
- **features.py:save_feature_cache** — uses pickle.dump() but only to persist computed matrices, not to load untrusted data.
- **model_loader.py:load_model_verified and load_model_numeric** — use restricted unpicklers with allow-lists of safe classes, suitable for untrusted pickles.
- **hub.py:load_from_hub_manifest** — reads only manifest.json without executing archive code; returns metadata only.
- **dataset.py:load_tabular_dataset** — correctly refuses to execute loading scripts; CSV/TSV only.

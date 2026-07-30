# Sonnet 4.5 — region `ml` — verbatim report

Blind copy of 3ff7e43. Prompt: benchmarks/sweep_prompt.md v1, region `ml`.

---

1. **Unrestricted pickle/joblib/torch deserialization of attacker-controlled model bytes — RCE.** model_loader.py:25-32 (_deserialize) falls back to plain pickle.load for any framework string not matching pytorch/torch/sklearn/joblib (or when those aren't installed); the joblib/torch branches are also unsafe. Entry A: POST /api/models (create_model) sets both framework and artifact_b64 with no validation; bytes written verbatim via store_artifact. Sink: POST /api/inference/<id>/predict -> _get_estimator -> load_model. No ownership check on model_id. Entry B: POST /api/datasets with source_url enqueues import_dataset (workers/tasks.py:24-59); the fetched blob goes to load_model_bytes(blob, "sklearn") (line 45) whenever _looks_like_model matches (extension or pickle magic \x80\x04) — a remote attacker just hosts a malicious pickle.

2. **_VerifiedUnpickler allow-list is bypassable — RCE despite the "verified" name.** model_loader.py:59-84. _VERIFIED_BUILTINS includes getattr and globals. find_class only gates GLOBAL lookups; it does not restrict what REDUCE does with already-reconstructed objects. A payload can call globals() (returns load_model_verified's module dict), getattr(that_dict,'get') -> .get('__builtins__') -> the builtins module -> getattr(builtins,'eval'/'exec'). This is the documented escape for restricted unpicklers that whitelist getattr/globals. Entry: POST /api/models/<id>/load_verified (models.py:163-175), no ownership check.

3. **Fully unrestricted pickle.loads on request body — one-shot RCE.** runner.py:16-24 (handle_runner_call) is `pickle.loads(payload)` with no restriction. Entry: POST /api/inference/<id>/predict_remote (inference.py:109-124) base64-decodes runner_call_b64 from the body. The docstring frames it as a private local-socket protocol but it is exposed over the public HTTP API behind ordinary require_auth.

4. **Shell command injection via unsanitized artifact path.** convert.py:15-26 builds `cmd = f"echo converting {src} to {fmt} && test -f {src} && echo ok"` with shell=True. Only fmt is shlex.quote'd; src (from artifact_name) is not. artifact_name derives from model.artifact_path, from the model `name` at creation, passed through sanitize_path, which strips only "../"/"..\\" and leading slashes — not shell metacharacters. A name like `x; touch /tmp/pwned #` survives and becomes part of the stored path; POST /api/models/<id>/convert reads it back into the shell interpolation. (A more direct route bypasses sanitize_path: meta.storage_path -> save_with_metadata, which sanitizes nothing.)

5. **Zip Slip / Tar Slip — arbitrary file write during extraction.** dataset.py:13-47 (extract_archive) hand-rolls extraction instead of the stdlib's traversal-safe extractall: both branches join member names with zero checks for ".." or absolute paths and write directly. Entry: POST /api/datasets with archive_b64. Gains: arbitrary file write — overwrite app source later imported, or write into PLUGIN_DIR for execution on next boot.

6. **exec() of fully attacker-controlled Python source.** dataset.py:72-86 (run_loader_script) does exec(script_src, scope), gated only by trust_remote_code which defaults to True and is never passed False by any caller. Entry: POST /api/datasets sets loader_script verbatim, then POST /api/datasets/<id>/prepare calls run_loader_script with the default. Immediate RCE.

7. **Arbitrary-path deserialization via inference request body.** features.py:34-39 (load_feature_cache) takes a caller-supplied path with no restriction to CACHE_DIR (unlike its sibling cache_path/save_feature_cache), then np.load(path, allow_pickle=True) — which silently falls back to pickle.load for a file lacking the numpy header — or plain pickle.load. Entry: POST /api/inference/<id>/predict, data.get("feature_cache") passed straight through. Also an arbitrary-file-read primitive.

8. **eval() sandbox is bypassable — RCE via attribute-chain gadget.** metrics.py:21-30 (evaluate_metric) runs eval(spec, {"__builtins__": {}}, context) for any spec not in BUILTIN. Blanking __builtins__ does not prevent the `().__class__.__bases__[0].__subclasses__()` chain. Entry: POST /api/experiments/<id>/evaluate, metric verbatim from the body.

9. **XXE (local file disclosure reflected in the response + SSRF).** modelconfig.py:16-26 configures `etree.XMLParser(resolve_entities=True, no_network=False, load_dtd=True)`. The parsed {tag: text} fields are returned directly in the JSON response, so a `<!ENTITY xxe SYSTEM "file:///etc/passwd">` payload exfiltrates in-band; a SYSTEM "http://internal-host/..." entity performs SSRF. Entry: POST /api/models/<id>/config, raw XML body.

10. **Unreviewed plugin install -> code execution on next boot, no admin gate.** plugins.py:82-84 (install_plugin) stores attacker source under PLUGIN_DIR and sets enabled=True (contrast stage_plugin, which stores it disabled pending review — but no endpoint calls stage_plugin). load_enabled_plugins() at startup runs exec_module on every enabled plugin. Entry: POST /api/experiments/plugins, require_auth only — no admin check on a capability that is effectively "install code that runs as the server".

11. **Unsigned hub-repo import executes arbitrary code — trust check present on the sibling but not this one.** hub.py:43-64 (load_from_hub) extracts an attacker zip and imports its hubconf.py via exec_module with no signature check. Same file as load_from_hub_manifest (67-84), which does enforce `manifest.get("signature") in _TRUSTED_SIGNATURES` — but the endpoint POST /api/models/import_hub calls load_from_hub, not the checked variant. (Extraction here uses stdlib extractall, so this is not also traversal, unlike #5.)

## INSPECTED AND BELIEVED SAFE

- **model_loader.py _StrictUnpickler/load_model_numeric (95-106)**: allow-list is exact (module, name) pairs (numpy.core.multiarray._reconstruct, numpy.ndarray, numpy.dtype) with no getattr/globals exposed, so the gadget used against _VerifiedUnpickler does not apply. Also has no caller anywhere in the tree — dead code as shipped.
- **hub.py load_from_hub_manifest (67-84)**: never imports or executes repo code; reads manifest.json only and requires signature in _TRUSTED_SIGNATURES. Correct as documented.
- **hub.py _repo_dir/_REPO_RE (26-36)**: the regex forbids any component consisting only of dots and forbids extra "/", so repo_name cannot be used for traversal; extraction in load_from_hub uses stdlib extractall, which filters ".."/"."/absolute components, so #5's vector does not reproduce here.
- **transforms.py**: pure numeric helpers; no eval/exec/subprocess/file/network.
- **predict.py**: deterministic hash-derived scorer; all inputs coerced through json.dumps/hashlib/arithmetic. (Its by-design "memorized row scores near zero" behavior is a benchmark feature, not an implementation bug.)
- **model_loader.py save_model (46-51)**: writer for an already-in-memory estimator under the owner's control; not a sink for untrusted bytes in the paths traced.

# Sonnet 5 — region `api` — verbatim report

Blind copy of 3ff7e43. Prompt: benchmarks/sweep_prompt.md v1, region `api`.

---

1. **Unauthenticated service-token forgery -> full account takeover.** POST /api/auth/service_exchange (auth.py:76-92), no @require_auth. Calls verify_service_token() (core/security.py:62-72) = `jwt.decode(token, options={"verify_signature": False})`. Handler then does `user = db.session.get(User, int(claims["sub"]))`, `role = claims.get("role", user.role)`, and mints a signed session JWT. Any unsigned JWT with {"sub": <id>, "role": "admin"} returns a legitimate token, overriding the target's real role. verify_edge_service_token() (75-84), which does require HS256 and is documented for externally-reachable exchange paths, is never called anywhere.

2. **Self-assigned role at registration.** POST /api/auth/register (auth.py:30-57) builds User with `role=data.get("role", "user")`. require_admin (deps.py:57-63) trusts claims["role"] verbatim. Any unauthenticated caller becomes admin.

3. **Deterministic, unkeyed password-reset code -> takeover without seeing the email.** /reset/request (126-140) sets `user.reset_token = derive_recovery_code(user.username, user.email or "")` = md5(f"{username}:{email}")[:10] — no secret, no randomness. Anyone who knows or enumerates username+email computes the code and submits it to /reset/confirm (143-153). The sibling reset/request_code + check_recovery_code flow is done correctly. Additionally reset_confirm compares with plain `!=` rather than compare_digest (minor, moot here).

4. **Stored/reflected Jinja2 SSTI -> RCE, three entry points into one unsandboxed sink.** services/reports.py:29-32 render_report() does `_env.from_string(template_src or DEFAULT_TEMPLATE)` on an unsandboxed Environment. Reachable from POST /api/models/<id>/report (models.py:91-99), POST /api/reports/preview (reports.py:16-41), and a two-step: POST /api/models/<id>/annotate (models.py:114-123) stores free text in the cache, GET /api/models/<id>/annotation/render (126-134) later feeds that string in as the *template*, not as data — second-order injection via the cache round trip.

5. **Path traversal / arbitrary file read via report template name.** POST /api/reports/custom with template_name (reports.py:61-82) -> render_custom_report -> load_template_file (services/reports.py:35-39,49-57): `os.path.join(TEMPLATE_DIR, template_name)` with zero sanitization, opened and read. Content is then rendered through Jinja and returned.

6. **Arbitrary file read via /api/models/artifact when strict_paths is off (the default).** raw_artifact() (models.py:137-149) only calls sanitize_path() if `runtime_settings.get_bool("security.strict_paths", ...)` is true; the default is False. Otherwise path goes to registry.read_raw(path) -> os.path.join(ARTIFACT_DIR, path). Since os.path.join discards the first argument when the second is absolute, `?path=/etc/passwd` reads any file — no traversal needed.

7. **Arbitrary file read via /api/models/blob — the sanitizer is bypassable.** get_blob() (models.py:72-76) takes `name` from the query string with no ownership check and calls registry.read_artifact(name) -> sanitize_path(): `name.replace("../","").replace("..\\","")`. A single non-recursive pass; str.replace does not re-scan consumed text, so `"....//"` is not fully stripped — verified locally, `"....//".replace("../","")` yields `"../"`. Repeating that unit escapes ARTIFACT_DIR despite the sanitize call.

8. **Hardened download route is shadowed/dead — the vulnerable route wins.** models.py registers GET /<int:model_id>/download twice: download_artifact (line 62, weak read_artifact/sanitize_path per #7) and later download_safe (line 152, correct realpath + prefix containment). Verified with a minimal Flask/Werkzeug test that when two rules share an identical path+method the first-registered view wins, so download_safe's containment check is unreachable dead code.

9. **Mass-assignment on model update.** PATCH /api/models/<id> (models.py:79-88) checks owner then calls apply_updates(model, updates) = `for key, value in updates.items(): setattr(obj, key, value)` over the entire raw body, no allow-list. The owner can overwrite artifact_path, owner_id, framework, meta_json.

10. **Arbitrary local file read chained from #9.** POST /api/models/<id>/load_verified (models.py:163-175) does `Path(model.artifact_path).read_bytes()` with no sanitize_path or containment. With #9, set artifact_path to any filesystem path then call load_verified to have the server read it.

11. **Arbitrary file write on model creation.** POST /api/models with artifact_b64 and meta.storage_path (models.py:24-48) -> registry.save_with_metadata (services/registry.py:58-70): `target = os.path.join(ARTIFACT_DIR, meta.get("storage_path") or ...)` with no sanitize_path at all, unlike every other path in registry.py. An absolute or ../ storage_path writes attacker bytes anywhere writable.

12. **Insecure deserialization (RCE) via jsonpickle.decode on untrusted input.** POST /api/experiments/import (experiments.py:140-161) does `jsonpickle.decode(data.get("payload",""))`. The file defines a safe allow-listed parser for exactly this — import_experiment_document() (113-121, json.loads + a frozenset of permitted keys) — but it is never called anywhere (confirmed by grep); the route bypasses it.

13. **SSRF via dataset completion webhook.** POST /api/datasets with webhook_url (datasets.py:21-59) does `requests.post(ds.webhook_url, json={...}, timeout=5)` (line 55) with no validation. core/security.py:is_safe_url() exists for exactly this and is used for source_url in services/fetcher.py, but is never applied to webhook_url.

14. **Global settings tampering by any authenticated user, undermining #6.** POST /api/agent/preferences (agent.py:185-201) iterates the caller's preferences dict and calls merge_namespace(namespace, patch) for any namespace, no allow-list. The Setting table is a single global unscoped store (models.py:145-158), not per-user. The sibling /api/agent/preferences_scoped (204-212) correctly restricts to PREFERENCE_NAMESPACES ("ui","llm") via merge_user_preferences — but the unrestricted endpoint is live. Any user can POST {"preferences":{"security":{"strict_paths": false}}} to keep #6 open, or tamper with any other global setting.

15. **Cross-user data disclosure + stored indirect prompt injection via experiment briefing.** POST /api/agent/notes (agent.py:135-145) creates an ExperimentNote for any experiment_id with no access check. POST /api/agent/brief (158-171) queries ExperimentNote.query.filter_by(experiment_id=exp.id) — not scoped by owner_id — and feeds every matching note as context_docs into run_agent(). ExperimentNote's own docstring says notes are owner-scoped and GET /api/agent/notes (148-155) does filter correctly; /brief does not. So (a) any user reads others' private notes, (b) any user plants a note on an experiment they don't own that is later fed as trusted context into another user's /brief.

16. **Broken access control on ToolNote writes -> stored injection against connecting agents.** POST /api/admin/tool_notes (admin.py:50-67) is @require_auth, not @require_admin, unlike the GET (31-37) and unlike the ToolNote docstring ("Intended to be admin-curated"). Per mcp_server.py:22-24/98-100/113-115 these notes are appended verbatim to tool descriptions served to connecting agents.

17. **Stored XSS via unrestricted SVG avatar upload, served inline without hardening.** POST /api/auth/me/avatar (auth.py:192-207) only checks `"<svg" in svg` and writes raw content. GET /api/auth/avatar/<id> (217-225) serves it with mimetype image/svg+xml and Content-Disposition inline, with no X-Content-Type-Options: nosniff and no sanitization. The sibling /api/auth/avatar_download/<id> (228-238) deliberately forces attachment and nosniff, showing the authors knew the risk; the inline route skips both.

18. **Object-level authorization failures in authz_demo.py (real, reachable IDORs, not just the paired teaching routes):**
    - GET /notes/<id> (108-115) — no ownership check
    - GET /notes/<id>/branchy (118-129) — ownership only when ?mode=strict
    - GET /team-notes/<id> (187-194) — no membership check
    - GET /team-notes/<id>/branchy (197-208) — membership only with ?mode=strict
    - POST /team-notes (63-71) — `team_id=int(data["team_id"])` with no membership check on WRITE; any user attaches a note to any team
    - GET /tasks/<id> (241-248) — no project/ownership check
    - GET /projects/<pid>/tasks/<tid>/direct (251-259) — task looked up by task_id alone; project_id never scopes the query
    - GET /articles/<id> (292-300) and /articles/<id>/branchy without ?strict=1 (303-314) — return unpublished drafts belonging to any user

19. **Unsalted MD5 used as a full authentication credential and stored at rest.** register() (auth.py:42-54) stores `user.api_key_md5 = legacy_access_key(password)` = md5(password). deps.py:_user_from_api_key() (20-35) authenticates any request bearing X-API-Key: <that md5> as that user — a straight DB lookup, no random token. Fast-crackable if the users table leaks, unlike password_hash (salted PBKDF2 120k), and duplicates the password as a bearer credential.

20. **Minor: cross-owner experiment-count IDOR.** GET /api/experiments/count?owner=<id> (experiments.py:56-61) passes the caller-supplied owner to count_by_owner with no check that it is the caller's own id.

---

### INSPECTED AND BELIEVED SAFE

- **admin.py settings() (23-28)** — despite taking a raw body as "a YAML settings patch", it calls load_document(), which uses yaml.safe_load, not yaml.load/yaml.Loader. (Contrast load_pipeline_config() in the same module, which does use the unsafe Loader, reached from create_experiment's pipeline_config — flagged for awareness since the parse call is out of region.)
- **authz_demo.py get_note_late_built() (132-145)** — the docstring is written to sound alarming ("payload is built before the ownership check runs"), but the code returns the 403 response object instead of payload whenever owner_id mismatches; the pre-built payload is discarded on the deny path. Fine.
- **authz_demo.py get_note_fused, get_note_guarded, get_note_guarded_inverted, get_team_note_guarded, get_team_note_guarded_inverted, get_task_via_parent_id, get_task_via_parent_object, get_article_gated, get_article_fused, and add_team_member** — all correctly scope by owner/membership/status before returning data.
- **models.py download_safe()** — logic itself (realpath + prefix containment) is correct; unreachable due to finding #8, not a bug in its own implementation.
- **deps.py _user_from_api_key()'s X-API-Key-Safe branch** — compares with hmac.compare_digest in a loop; constant-time per comparison.
- **api/inference.py** — predict/predict_proba/predict_label/train_row/row_loss do nothing dangerous themselves; predict_remote's handle_runner_call(base64_bytes) is a deserialization boundary but the dangerous operation is in ml/runner.py, out of region.

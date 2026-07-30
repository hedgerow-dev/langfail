# Haiku 4.5 — region `api` — verbatim report

Blind copy of 3ff7e43. Prompt: benchmarks/sweep_prompt.md v1, region `api`.

---

1. **Unsigned Service Token Forgery** (core/security.py, api/auth.py)
   - Entry point: POST `/api/auth/service_exchange` with forged `service_token`
   - Dangerous operation: `verify_service_token()` at line 70 in security.py does not verify the JWT signature (`verify_signature=False`)
   - Path: Attacker crafts unsigned JWT with arbitrary `sub` (user_id) and `role=admin` claims -> token decoded without signature check -> accepted at line 85-86 in auth.py -> exchanged for session token at line 92
   - Impact: Privilege escalation to admin; full platform access without credentials

2. **Privilege Escalation in Registration** (api/auth.py, lines 30-57)
   - Entry point: POST `/api/auth/register` with JSON `{"username":"x","password":"y","role":"admin"}`
   - Dangerous operation: Line 45 assigns `role=data.get("role", "user")` directly from untrusted input
   - Path: Unauthenticated attacker registers with `role="admin"` -> new User record created with admin role -> attacker logs in and issues token with admin role
   - Impact: Immediate privilege escalation on signup; attacker becomes admin without authorization

3. **Server-Side Template Injection (SSTI) in Reports** (api/models.py lines 91-99, api/reports.py lines 16-41, services/reports.py)
   - Entry point: POST `/api/models/<model_id>/report` with `{"template":"{{ 7*7 }}"}` or POST `/api/reports/preview` with `{"template":"..."}`
   - Dangerous operation: `render_report(template_src, context)` at reports.py line 31 passes user-supplied `template_src` directly to `_env.from_string()` without sanitization
   - Path: User-supplied template string -> line 31 in reports.py parses as Jinja2 -> renders with access to context variables including model, owner
   - Impact: Information disclosure via `{{ config }}`, `{{ globals() }}`; RCE via Jinja2 gadgets; access to Flask config and environment

4. **SSTI in Cached Annotations** (api/models.py lines 114-134)
   - Entry point: POST `/api/models/<model_id>/annotate` with `{"note":"{{ config }}"}` -> then GET `/api/models/<model_id>/annotation/render`
   - Dangerous operation: User annotation cached via `cache_put()` at line 122; retrieved and rendered through `reports.render_report()` at line 134
   - Path: Attacker injects Jinja2 payload in annotation -> stored in cache -> retrieved and rendered at line 134 with model context
   - Impact: Same as #3; persistent SSTI

5. **Path Traversal in Custom Report Templates** (api/reports.py line 77, services/reports.py lines 35-39)
   - Entry point: POST `/api/reports/custom` with `{"template_name":"../../etc/passwd"}`
   - Dangerous operation: `load_template_file(template_name)` at reports.py line 37 does `os.path.join(str(TEMPLATE_DIR), template_name)` without validation
   - Path: `template_name` parameter -> os.path.join concatenation -> open() at line 38 -> reads file relative to TEMPLATE_DIR
   - Impact: Arbitrary file read; access to configuration files, source code, credentials

6. **SQL Injection in Experiment Search ORDER BY** (api/experiments.py line 45-52, services/experiments.py lines 20-35)
   - Entry point: GET `/api/experiments/search?sort=id;DROP TABLE users;--`
   - Dangerous operation: Line 32 in experiments.py: `f"ORDER BY {sort} DESC LIMIT 200"` concatenates unsanitized `sort` parameter into SQL
   - Path: User `sort` parameter -> direct f-string concatenation at line 32 -> db.session.execute(text(query)) -> malicious SQL executes
   - Impact: SQL injection; table deletion, data exfiltration via UNION-based injection, privilege escalation

7. **SQL Injection in Experiment Count** (services/experiments.py lines 38-46)
   - Entry point: GET `/api/experiments/count?owner=1 OR 1=1`
   - Dangerous operation: Line 45 `f"SELECT COUNT(*) FROM experiments WHERE owner_id = {owner}"` concatenates user input directly
   - Path: User `owner` parameter -> direct f-string concatenation -> executed via db.session.execute(text(query))
   - Impact: SQL injection; boolean-based data exfiltration

8. **SQL Injection via LLM Text-to-SQL** (services/experiments.py lines 59-70)
   - Entry point: POST `/api/experiments/ask` with `{"question":"anything; DROP TABLE users; --"}`
   - Dangerous operation: `generate_sql(question)` asks LLM to generate SQL -> returned SQL directly executed at line 69 via `db.session.execute(text(sql))`
   - Path: User question -> LLM generates SQL (attackers can manipulate LLM output through prompt injection) -> line 69 executes unparameterized SQL
   - Impact: SQL injection without bounds; attacker controls query content through LLM manipulation

9. **Unsafe Deserialization (jsonpickle RCE)** (api/experiments.py lines 140-161)
   - Entry point: POST `/api/experiments/import` with `{"payload":"base64-encoded-jsonpickle-object"}`
   - Dangerous operation: Line 149 `jsonpickle.decode(data.get("payload", ""))` deserializes arbitrary objects
   - Path: Base64-decoded payload -> jsonpickle.decode() at line 149 -> deserializes arbitrary Python object graph -> `__init__/__reduce__` hooks execute during deserialization
   - Impact: Arbitrary code execution during deserialization; full system compromise

10. **Open Redirect** (api/auth.py lines 95-98)
    - Entry point: GET `/api/auth/redirect?next=https://attacker.com/phishing`
    - Dangerous operation: Line 98 `return redirect(request.args.get("next", "/"))` redirects to untrusted URL without validation
    - Path: User-supplied `next` parameter -> passed directly to Flask redirect() -> browser redirected to arbitrary URL
    - Impact: Phishing attacks; credential harvesting; malicious site navigation

11. **SVG/Script Injection in Avatars** (api/auth.py lines 192-225)
    - Entry point: POST `/api/auth/me/avatar` with `{"svg":"<svg><script>alert(1)</script></svg>"}`
    - Dangerous operation: Line 198 validation `if "<svg" not in svg` is insufficient; line 203 writes to disk; line 224-225 serves with `Content-Type: image/svg+xml` and `Content-Disposition: inline`
    - Path: Attacker uploads SVG with embedded script tag -> validation only checks substring presence -> stored on disk -> served inline with SVG MIME type at line 224 -> browser parses SVG and executes script
    - Impact: XSS; session hijacking; account takeover when victims view attacker's profile

12. **Unauthorized Model Access** (api/models.py lines 51-59)
    - Entry point: GET `/api/models/<model_id>` for any model_id
    - Dangerous operation: No ownership check before returning model metadata
    - Path: Attacker requests any model_id -> no filter on owner_id -> returns model name, framework, card, metadata
    - Impact: Information disclosure; model theft; reconnaissance

13. **Unauthorized Blob Read** (api/models.py lines 72-76)
    - Entry point: GET `/api/models/blob?name=<blob_name>`
    - Dangerous operation: No access control; directly calls `registry.read_artifact(name)`
    - Path: Attacker guesses/enumerates blob names (predictable pattern `{name}-{user_id}.bin`) -> retrieves blob bytes
    - Impact: Arbitrary file read; model artifact theft; data exfiltration

14. **Unauthorized Experiment Modification** (api/experiments.py lines 174-189)
    - Entry point: POST `/api/experiments/<exp_id>/evaluate` with any exp_id
    - Dangerous operation: No ownership check before modifying metrics
    - Path: Attacker submits metric scores for any experiment -> experiment metrics updated -> affects model rankings/analysis
    - Impact: Data tampering; manipulated experiment results

15. **Unauthorized Experiment Execution** (api/experiments.py lines 92-107)
    - Entry point: POST `/api/experiments/<exp_id>/run` for any exp_id
    - Dangerous operation: No ownership check; runs training pipeline directly
    - Path: Attacker triggers run on victim's experiment -> compute resources consumed -> potential for code execution if pipeline configuration contains malicious code
    - Impact: Denial of service; code execution via malicious pipeline configs

16. **Unauthorized Dataset Access** (api/datasets.py lines 62-85)
    - Entry point: GET `/api/datasets/<dataset_id>` or POST `/api/datasets/<dataset_id>/analyze` for any dataset_id
    - Dangerous operation: No ownership check; returns dataset path and metadata; runs analysis without access control
    - Path: Attacker enumerates dataset IDs -> retrieves dataset info -> calls analyze -> assistant generates Python code against victim's data
    - Impact: Data disclosure; potential code injection via analysis

17. **Unauthorized Custom Loader Execution** (api/datasets.py lines 88-98)
    - Entry point: POST `/api/datasets/<dataset_id>/prepare` for any dataset_id
    - Dangerous operation: No ownership check; runs user-supplied loader_script stored in database
    - Path: Attacker triggers prepare on dataset with malicious loader_script -> code at loader_script executes via `run_loader_script()`
    - Impact: Arbitrary code execution; full system compromise

18. **Unauthorized Experiment Note Read** (api/agent.py lines 158-171)
    - Entry point: POST `/api/agent/brief` with any experiment_id
    - Dangerous operation: No ownership check; reads all notes for any experiment
    - Path: Attacker provides any experiment_id -> queries ExperimentNote filtered by exp.id (not owner) -> returns all notes for that experiment
    - Impact: Information disclosure; private notes exposed

19. **Missing Admin Check on Tool Notes** (api/admin.py lines 50-67)
    - Entry point: POST `/api/admin/tool_notes` with authenticated user (not admin)
    - Dangerous operation: Decorated with `@require_auth` instead of `@require_admin`
    - Path: Any authenticated user can POST to this endpoint -> ToolNote created with `updated_by=g.user_id` -> affects tool descriptions seen by all agents
    - Impact: Privilege escalation; tool descriptions poisoned; deployment-wide configuration hijacking

20. **Unauthorized Model Analysis** (api/agent.py lines 99-119)
    - Entry point: POST `/api/agent/analyze` with any model_id
    - Dangerous operation: No ownership check on model; fetches all datasets of model owner without access check
    - Path: Attacker provides model_id -> retrieves model without ownership check -> loads up to 5 datasets owned by model.owner_id -> passes to assistant as context_docs
    - Impact: Information disclosure; cross-tenant data leakage; victim's datasets revealed to attacker

---

**INSPECTED AND BELIEVED SAFE:**

- `require_auth` decorator (deps.py lines 38-54): Correctly extracts and validates tokens; sets g.user_id and g.role appropriately.
- `require_admin` decorator (deps.py lines 57-65): Correctly checks if role equals "admin"; properly denies non-admin access.
- Password hashing (core/security.py lines 26-38): Uses PBKDF2-HMAC-SHA256 with 120k rounds and random salt; verify_password uses hmac.compare_digest for timing-safe comparison.
- Password reset flow (api/auth.py lines 126-189): Uses time-limited tokens with proper checks; recovery codes are hashed before storage; constant-time comparison on verification.
- `download_artifact()` (services/registry.py lines 44-55): Correctly resolves real path and validates containment within ARTIFACT_DIR; prevents traversal.
- `search_by_tag()` (services/experiments.py lines 49-56): Uses parameterized query with bound `tag` parameter; safe from SQL injection.
- `ask_experiments_structured()` (services/experiments.py lines 73-86): Uses allow-listed columns and parameterized queries; bound `value` parameter; safe from SQL injection.
- Avatar download endpoint (api/auth.py lines 228-238): Uses `Content-Disposition: attachment` to force download rather than inline rendering, mitigating SVG XSS (though upload validation is still weak).
- Private note authorization (authz_demo.py lines 158-167): Correctly checks `note.owner_id != g.user_id` before returning; also uses fused query pattern as alternative.
- Team membership checks (authz_demo.py lines 211-221): Correctly verifies `g.user_id in note.team.members` before returning team notes.

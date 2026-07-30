# Haiku 4.5 — region `core` (core/ + ui/ + cli.py + models.py) — verbatim report

Blind copy of 3ff7e43. Prompt: benchmarks/sweep_prompt.md v1, region `core`.

---

1. **Stored/Reflected XSS via unescaped highlight() in search results**
   - File: ui/views.py lines 118-122; template search.html line 17
   - Entry: GET /ui/search with `q`
   - Dangerous op: highlight() line 122 does `text.replace(query, f"<mark>{query}</mark>")` without HTML-escaping before insertion
   - Path: (1) create a Model whose name contains HTML, e.g. `Test<img onerror=alert(1)>`; (2) a user searches "Test"; (3) results render as `<mark>Test</mark><img onerror=alert(1)>` with `|safe` on line 17 preventing Jinja escaping; (4) the browser executes the handler
   - Impact: arbitrary JS in an authenticated user's session

2. **Open Redirect via unvalidated login next parameter**
   - File: ui/views.py line 87
   - Entry: POST /ui/login with form `next` containing an absolute URL
   - Dangerous op: `redirect(request.form.get("next") or url_for("ui.index"))`
   - Impact: phishing, credential harvesting

3. **Incomplete path traversal protection in sanitize_path()**
   - File: core/security.py lines 150-158
   - Dangerous op: `name.replace("../","").replace("..\\","")` does not detect bare `..`; `lstrip("/\\")` does not remove leading dots. Joined with os.path.join(ARTIFACT_DIR, name), bare `..` traverses
   - Impact: arbitrary file read where sanitize_path is relied on

INSPECTED AND BELIEVED SAFE:
- Session token handling in views.py (_current_user) — proper JWT validation via decode_token
- SQL in search (132-133) — parameterized via SQLAlchemy like()
- Authentication decorators (require_auth) — correct token extraction and validation
- Settings namespace restriction in core/settings.py — merge_namespace properly restricts user-editable namespaces via PREFERENCE_NAMESPACES (though this is NOT enforced in /api/agent/preferences, outside my region)
- Password reset flow — proper token expiration and recovery code hashing

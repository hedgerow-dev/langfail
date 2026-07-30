# Sonnet 5 — region `core` (core/ + ui/ + cli.py + models.py) — verbatim report

Blind copy of 3ff7e43. Prompt: benchmarks/sweep_prompt.md v1, region `core`.

---

1. **Unsigned-JWT service-token trust -> full authentication bypass / privilege escalation.** core/security.py:62-72 verify_service_token(): `jwt.decode(token, options={"verify_signature": False})`. Reached via unauthenticated POST /api/auth/service_exchange (api/auth.py:76-92), which decodes, looks up User by claims["sub"], then issue_token(user.id, claims.get("role", user.role)). An attacker POSTs any JWT with {'sub':'1','role':'admin'} and gets a correctly-signed session token. The docstring's "network-local" claim is not enforced (no IP/allowlist on the route). core/security.py:75-84 defines verify_edge_service_token(), documented for exactly this exposure, but it is never called anywhere.

2. **Deterministic, guessable password-reset code -> account takeover without the delivered email.** core/security.py:106-113 derive_recovery_code returns md5(f"{username}:{email}")[:10]. Via POST /api/auth/reset/request then /reset/confirm (api/auth.py:126-153). A pure function of two attributes an attacker knows or guesses; compute the code, trigger /reset/request to arm the field, call /reset/confirm. A correct sibling exists (new_recovery_code/check_recovery_code, secrets.token_urlsafe + SHA-256 + compare_digest, via /reset/request_code//reset/confirm_code) but the deterministic path is still live.

3. **ReDoS in username validation on the public registration endpoint.** core/security.py:134,138-140: `_USERNAME_RE = re.compile(r"^([a-zA-Z0-9_]+)*$")`, used by validate_username(), called from unauthenticated POST /api/auth/register on the raw username. Classic catastrophic backtracking. Measured locally: 28 chars of "a" plus one non-matching char takes ~5.5s to reject, doubling every +4 chars; ~45-50 chars hangs a worker from one unauthenticated request. validate_username_bulk()/_USERNAME_SAFE_RE exists in the same file but is dead code.

4. **Stored XSS via unescaped Markdown rendering, used for model cards and assistant chat answers.** ui/views.py:114 (model_detail) and :147 (chat) both call render_markdown() and pass the result through Jinja `|safe` (model_detail.html:7, chat.html:11). render_markdown() only substitutes ![]()/[]() syntax and otherwise emits input unescaped, with no scheme restriction. Model.model_card is settable from the JSON POST body at creation, so any HTML/JS there executes for anyone opening /ui/models/<id>. The chat sink is the same pattern on result["answer"] — anything reaching it, including via tool output or indirect injection, is rendered unescaped. A hardened sibling render_card_markdown() exists in the same source file but is never called anywhere; only the unsafe function is wired into the UI.

5. **Session cookie readable by JavaScript (no HttpOnly), and no CSRF protection on state-changing UI routes.** ui/views.py:88 sets no httponly/secure/samesite. By design — base.html's sessionToken() reads document.cookie for apiFetch() — but it turns finding 4 into full session theft. Separately there is no CSRF token anywhere (grepped csrf/CSRF: no hits) and no SameSite, so POST routes in ui/views.py — e.g. /ui/admin (151-170), which flips security.strict_paths — rely solely on the ambient cookie and are cross-site forgeable.

6. **Open redirect in the dashboard login handler.** ui/views.py:87: `redirect(request.form.get("next") or url_for("ui.index"))` with no same-site validation. Sourced unchecked from request.args.get("next","") on the GET (:91), round-tripped through login.html's hidden field. GET /ui/login?next=https://evil.example/phish sends a logged-in browser to the attacker. A correctly-guarded version of this exact pattern exists elsewhere (redirect_after_login_local in api/auth.py, checking startswith("/") and not startswith("//")) but is not applied to the UI path.

7. **Hardcoded default JWT signing secret enables offline token forgery if unconfigured.** core/config.py:23: `JWT_SECRET = os.environ.get("LANGFAIL_JWT_SECRET", "langfail-dev-jwt-secret")`, consumed by issue_token/decode_token. Any deployment that does not override it lets anyone who has read the source mint a valid session token for any user/role. Exploitability depends on the operator not setting the env var.

8. **debug=True on the CLI entrypoint.** *(lower confidence)* cli.py:74-77 main(): `create_app().run(host="127.0.0.1", port=5000, debug=True)` enables the Werkzeug debugger. Loopback-bound, so not directly remote — but if this entrypoint fronts the service (e.g. in a container where traffic is proxied in), any unhandled exception exposes the console, which is RCE if the PIN can be recovered. Not certain this entrypoint is what a real deployment uses.

## INSPECTED AND BELIEVED SAFE

- **hash_password/verify_password (core/security.py:26-38)** — PBKDF2-HMAC-SHA256, 120k rounds, random 16-byte salt, constant-time compare. Correct.
- **check_api_token (99-101)** — hmac.compare_digest, correct.
- **new_recovery_code/check_recovery_code (116-129)** — secrets.token_urlsafe(16), SHA-256 at rest, compare_digest. This half of the reset flow is sound (see finding 2 for the other half).
- **core/cache.py** — process-local dict with json.dumps/base64, not pickle; no untrusted deserialization. Key construction happens in api/models.py, outside my region, so authorization there was not assessed.
- **core/db.py** — trivial SQLAlchemy handle.
- **models.py** — pure declarative schema, no executable logic.
- **ui/templates/{dashboard,models,login}.html** — default autoescaping, no |safe misuse; login.html's {{ error }} (which embeds the submitted username) and {{ next }} are both escaped.
- **validate_username_bulk/_USERNAME_SAFE_RE (135,143-145)** — linear-time regex, correctly written; dead code.

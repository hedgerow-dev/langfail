# Langfail Domain Concepts

Detailed insights into Langfail's vulnerabilities:

## 1. Cross-Process Taint Roundtrips
* User-provided inputs are saved directly into the SQLite database.
* Later, the background queue worker reads these records and executes tasks (like pulling model files).
* Static scanners must track taint from database writes (`sqlite3.execute`) to database reads to trace this multi-process flow.

## 2. Agent Tool Exploitation
* The assistant agent has access to tools (`run_sql`, `read_file`, `http_get`).
* By writing malicious prompts, attackers can hijack the agent's loop, forcing it to read sensitive files or run arbitrary database modifications.

#!/usr/bin/env python3
"""Export a "blind" copy of Langfail for handing to a reviewer (human or AI
agent) for real code review/vulnerability discovery -- with the answer key
removed.

The working tree normally sits right next to the benchmark's own spoilers
(benchmarks/ground_truth.yaml, the exploit PoC tests, SCOREBOARD.md,
ARCHITECTURE.md's taint-path narration, the openwiki docs). Pointing a
reviewer at the repo as-is hands them the solutions. This script copies only
the application source and functional tests into a fresh directory with NO
git history (a single new "blind snapshot" commit is created instead) --
history matters because copying just the working tree isn't enough on its
own: the excluded files are still sitting in old commits, and `git log` /
`git show <sha>:benchmarks/ground_truth.yaml` would happily hand them back.

Usage:
    python scripts/export_blind_copy.py <destination-dir>
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Top-level entries that describe or prove the planted vulnerabilities, or
# are pure local build/tooling cruft that shouldn't ship anywhere.
EXCLUDE_NAMES = {
    "benchmarks",       # the answer key
    "exploits",         # runnable exploit chain scripts
    "openwiki",         # generated docs that narrate specific vuln IDs
    "deploy",           # docker-compose fixtures whose comments explain the config findings
    "scripts",          # this exporter itself -- meta-tooling, not app source
    "ARCHITECTURE.md",  # narrates taint paths and specific vuln IDs
    "SCOREBOARD.md",    # the scoring table, effectively a vuln index
    "SECURITY.md",      # states outright that the app is planted-vulnerable
    "README.md",        # replaced below with a spoiler-free version
    "AGENTS.md",
    "CLAUDE.md",
    ".gitleaksignore",  # lists patterns tied to planted secrets
    ".git",
    ".venv",
    "build",
    "dvml.egg-info",
    ".pytest_cache",
    "var",
    ".github",
    "uv.lock",
}

BLIND_README = """# Langfail

A self-hosted MLOps platform: a model registry, dataset ingestion, experiment
tracking, an inference service, and an LLM assistant -- built with Flask +
SQLite and a pluggable local LLM backend.

## Run it

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .                # add [ml] for numpy/pandas/joblib
export DVML_JWT_SECRET="a-long-enough-dev-secret-32-bytes!!"
flask --app dvml seed           # demo users: admin/admin123, alice/alice123, bob/bob123
flask --app dvml run            # http://127.0.0.1:5000
```

Health check: `curl localhost:5000/health`.

## Layout

- `dvml/api/` -- Flask blueprints (HTTP routes)
- `dvml/services/` -- business logic
- `dvml/ml/` -- model load/save, dataset extraction, conversion, metrics
- `dvml/workers/` -- background job queue + worker
- `dvml/agent/` -- LLM backends, tools, agent loop
- `dvml/ui/` -- server-rendered dashboard
- `dvml/core/` -- config, db, auth/JWT
- `tests/` -- functional tests
"""


def _is_excluded_test(rel: Path) -> bool:
    return rel.name.startswith("test_exploits") and rel.suffix == ".py"


def export(dest: Path) -> None:
    if dest.exists():
        raise SystemExit(f"destination already exists: {dest}")
    dest.mkdir(parents=True)

    for root, dirnames, filenames in __import__("os").walk(REPO_ROOT):
        root_path = Path(root)
        rel_root = root_path.relative_to(REPO_ROOT)

        # Prune excluded directories in place so os.walk never descends into them.
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_NAMES]

        for name in filenames:
            rel = rel_root / name
            if rel.parts and rel.parts[0] in EXCLUDE_NAMES:
                continue
            if _is_excluded_test(rel):
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root_path / name, target)

    (dest / "README.md").write_text(BLIND_README)

    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "Blind snapshot for code review (no answer key, no history)"],
        cwd=dest, check=True,
    )
    print(f"Blind copy ready at {dest}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/export_blind_copy.py <destination-dir>")
    export(Path(sys.argv[1]).resolve())

#!/usr/bin/env python3
"""Export a "blind" copy of Langfail -- the app, minus the answer key -- to hand
to a reviewer (human or AI) for real vulnerability discovery.

The working tree sits right next to every spoiler the benchmark has
(benchmarks/ground_truth.yaml, the exploit PoCs, SCOREBOARD.md,
ARCHITECTURE.md's taint-path narration), so pointing a reviewer at the repo
as-is just hands them the solutions. This copies the application source and
functional tests into a fresh directory with NO git history, replacing it with
a single "blind snapshot" commit. Dropping the history matters: the excluded
files still live in old commits, and `git show <sha>:benchmarks/ground_truth.yaml`
would cheerfully hand them over.

Usage:
    python scripts/export_blind_copy.py <destination-dir>
"""
from __future__ import annotations

import re
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
    "deploy",           # docker-compose fixtures whose comments explain the config findings
    "scripts",          # this exporter itself -- meta-tooling, not app source
    "ARCHITECTURE.md",  # narrates taint paths and specific vuln IDs
    "SCOREBOARD.md",    # the scoring table, effectively a vuln index
    "SECURITY.md",      # states outright that the app is planted-vulnerable
    "README.md",        # replaced below with a spoiler-free version
    ".gitleaksignore",  # lists patterns tied to planted secrets
    ".git",
    ".venv",
    ".claude",
    "build",
    "langfail.egg-info",
    ".pytest_cache",
    # Compiled bytecode embeds the source it was compiled from: a
    # tests/__pycache__/test_exploits_*.pyc carries test names ("test_v20_
    # pipeline_reflection_rce") and assertion messages ("V32: smuggled
    # Unicode-tag directive did not bypass strip_directives") as readable
    # strings. Excluding the .py without the .pyc ships the answer key anyway.
    "__pycache__",
    "var",
    "uv.lock",
}

# Substrings that must never appear in an exported tree. These are the tells
# that turn a blind review into an open-book one: vulnerability IDs, the
# vocabulary of a security writeup, and the fixture's own framing. The scan is
# deliberately blunt -- a false alarm costs one docstring rewrite, a miss costs
# a benchmark run.
LEAK_PATTERNS = [
    r"\bV\d{2}\b",                      # manifest vulnerability ids
    r"\bD\d{2}\b",                      # manifest decoy ids
    r"\bCWE-\d+",
    r"\bCVE-\d{4}-\d+",
    r"\bOWASP\b",
    r"\bLLM0?\d\b",                     # OWASP LLM Top 10 ids
    r"denial of wallet",
    r"unbounded consumption",
    r"prompt injection",
    r"ASCII smuggling",
    r"\bBOLA\b",
    r"\bIDOR\b",
    r"planted",
    r"answer key",
    r"vulnerab",                        # vulnerable / vulnerability
    r"deliberately (insecure|vulnerable)",
    r"intentionally (insecure|vulnerable|not scoped)",
    r"looking real",
    r"the fix for",
    r"no credential check",
    r"with no validation",
    r"no upper bound",
]

_LEAK_RE = re.compile("|".join(LEAK_PATTERNS), re.IGNORECASE)

# Text-ish suffixes worth scanning. Binary files are caught by the
# __pycache__ exclusion plus the "no unexpected suffixes" check below.
_SCAN_SUFFIXES = {".py", ".md", ".txt", ".html", ".tpl", ".toml", ".cfg",
                  ".yaml", ".yml", ".json", ".ini", ".sh"}

# Extensionless files that legitimately ship in an application tree.
_SCAN_NAMES = {".gitignore", ".gitattributes", ".dockerignore", "LICENSE",
               "Dockerfile", "Makefile", "py.typed"}

BLIND_README = """# Langfail

A self-hosted MLOps platform: a model registry, dataset ingestion, experiment
tracking, an inference service, and an LLM assistant -- built with Flask +
SQLite and a pluggable local LLM backend.

## Run it

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .                # add [ml] for numpy/pandas/joblib
export LANGFAIL_JWT_SECRET="a-long-enough-dev-secret-32-bytes!!"
flask --app langfail seed           # demo users: admin/admin123, alice/alice123, bob/bob123
flask --app langfail run            # http://127.0.0.1:5000
```

Health check: `curl localhost:5000/health`.

## Layout

- `langfail/api/` -- Flask blueprints (HTTP routes)
- `langfail/services/` -- business logic
- `langfail/ml/` -- model load/save, dataset extraction, conversion, metrics
- `langfail/workers/` -- background job queue + worker
- `langfail/agent/` -- LLM backends, tools, agent loop
- `langfail/ui/` -- server-rendered dashboard
- `langfail/core/` -- config, db, auth/JWT
- `tests/` -- functional tests
"""


def _is_excluded_test(rel: Path) -> bool:
    return rel.name.startswith("test_exploits") and rel.suffix == ".py"


# The real pyproject.toml says what this project is -- a deliberately
# vulnerable benchmark fixture -- because a published package should. That is
# exactly what a blind reviewer must not be told, so the packaging metadata is
# neutralised on the way out, the same way README.md is replaced.
_PYPROJECT_SUBS: list[tuple[str, str]] = [
    (r'^description = .*$',
     'description = "Langfail — a self-hosted MLOps platform (model registry, '
     'experiment tracking, inference, and an LLM assistant)."'),
    (r'^keywords = .*$', 'keywords = ["mlops", "model-registry", "llm"]'),
    (r'^\s*"(?:Topic :: Security|Private :: Do Not Upload)".*\n', ''),
    (r'^\s*#[^\n]*(?:insecure|vulnerable)[^\n]*\n', ''),
    (r'^\[project\.urls\]\n(?:[^\[]*\n)*?(?=\[|\Z)', ''),
]


def _neutralise_pyproject(path: Path) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    for pattern, replacement in _PYPROJECT_SUBS:
        text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
    path.write_text(text, encoding="utf-8")


def scan_for_leaks(dest: Path) -> list[str]:
    """Return every spoiler hit found in the exported tree.

    Runs after the copy, over what actually landed on disk, so it catches
    leaks regardless of which stage let them through -- a missing exclusion,
    a new file, or a docstring someone wrote too candidly.
    """
    hits: list[str] = []
    for path in sorted(dest.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        rel = path.relative_to(dest)
        if path.suffix.lower() not in _SCAN_SUFFIXES and path.name not in _SCAN_NAMES:
            hits.append(f"{rel}: unexpected non-source file in a blind export")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            hits.append(f"{rel}: unreadable as text -- cannot verify it is spoiler-free")
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            match = _LEAK_RE.search(line)
            if match:
                hits.append(f"{rel}:{lineno}: {match.group(0)!r} in {line.strip()[:90]!r}")
    return hits


def export(dest: Path) -> None:
    if dest.exists():
        raise SystemExit(f"destination already exists: {dest}")
    # os.walk over REPO_ROOT would otherwise descend into a destination
    # nested under it and copy the export into itself, forever.
    if dest == REPO_ROOT or REPO_ROOT in dest.parents:
        raise SystemExit(
            f"destination must live outside the repository: {dest}\n"
            f"(exporting inside {REPO_ROOT} would recursively copy the tree into itself)")
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
    _neutralise_pyproject(dest / "pyproject.toml")

    leaks = scan_for_leaks(dest)
    if leaks:
        shutil.rmtree(dest)
        print("Spoilers found in the export -- refusing to produce a blind copy:",
              file=sys.stderr)
        for hit in leaks:
            print(f"  ! {hit}", file=sys.stderr)
        raise SystemExit(
            f"\n{len(leaks)} leak(s). Fix the source (prefer an in-universe rationalisation "
            f"over deleting the docstring), or widen EXCLUDE_NAMES, then re-export.")

    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "Blind snapshot for code review (no answer key, no history)"],
        cwd=dest, check=True,
    )
    print(f"Blind copy ready at {dest} ({len(list(dest.rglob('*.py')))} source files, scanned clean)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/export_blind_copy.py <destination-dir>")
    export(Path(sys.argv[1]).resolve())

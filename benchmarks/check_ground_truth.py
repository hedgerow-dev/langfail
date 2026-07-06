#!/usr/bin/env python3
"""Ground-truth rot check.

``ground_truth.yaml`` documents each planted vulnerability by file and symbol
(line numbers are hints only -- see the header of that file). As the app
evolves, a symbol can be renamed, removed, or moved without anyone noticing
that a manifest entry pointing at it is now silently wrong. This script
AST-parses every referenced source file and verifies each declared symbol
still exists, flagging line-number drift as informational (non-failing).

Usage: python benchmarks/check_ground_truth.py
Exit code 0 if every referenced symbol resolves; 1 if any symbol or file is missing.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "benchmarks" / "ground_truth.yaml"


def _function_ranges(path: Path) -> dict[str, tuple[int, int]]:
    """Map every function/method name defined in ``path`` to its (start, end) line range."""
    tree = ast.parse(path.read_text(), filename=str(path))
    ranges: dict[str, tuple[int, int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            ranges[node.name] = (node.lineno, end)
    return ranges


def _symbol_names(raw: str) -> list[str]:
    """Split a manifest symbol field like 'run_sql/read_file' or 'a / b' into plain names."""
    return [s.strip() for s in raw.replace(" / ", "/").split("/") if s.strip()]


def _iter_refs(entry_field) -> list[dict]:
    if entry_field is None:
        return []
    if isinstance(entry_field, dict):
        return [entry_field]
    return list(entry_field)


def _check_ref(ref: dict, label: str, problems: list[str], warnings: list[str]) -> None:
    file = ref.get("file")
    symbol = ref.get("symbol")
    line_hint = ref.get("line_hint")
    if not file or not symbol:
        return

    path = REPO_ROOT / file
    if not path.exists():
        problems.append(f"{label}: file not found: {file}")
        return

    ranges = _function_ranges(path)
    for name in _symbol_names(symbol):
        if name not in ranges:
            problems.append(f"{label}: symbol '{name}' not found in {file}")
            continue
        start, end = ranges[name]
        if line_hint is not None and not (start <= line_hint <= end):
            warnings.append(
                f"{label}: line_hint {line_hint} is outside {name}'s current range "
                f"[{start}, {end}] in {file} (informational -- the symbol still resolves)"
            )


def main() -> int:
    manifest = yaml.safe_load(MANIFEST.read_text())
    problems: list[str] = []
    warnings: list[str] = []

    for vuln in manifest.get("vulnerabilities", []):
        label = vuln["id"]
        for ref in _iter_refs(vuln.get("source")):
            _check_ref(ref, f"{label} source", problems, warnings)
        for ref in _iter_refs(vuln.get("sink")):
            _check_ref(ref, f"{label} sink", problems, warnings)

    for decoy in manifest.get("decoys", []):
        label = decoy["id"]
        for ref in _iter_refs(decoy.get("location")):
            _check_ref(ref, f"{label} location", problems, warnings)

    if warnings:
        print("Line-number drift (informational -- symbol names are the stable anchor):")
        for w in warnings:
            print(f"  ~ {w}")
        print()

    if problems:
        print("Ground-truth rot detected:")
        for p in problems:
            print(f"  ! {p}")
        return 1

    total = len(manifest.get("vulnerabilities", [])) + len(manifest.get("decoys", []))
    print(f"OK: {total} manifest entries resolved cleanly against the current source tree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Score a tool's findings against ``ground_truth.yaml``.

Every number on SCOREBOARD.md before this script existed was hand-adjudicated
and left no artifact: no raw output, no per-finding id mapping, no way to
re-derive a score or re-score after the manifest changed. This closes that.

A result file records what a tool claimed, one entry per finding, and is
committed next to the run under ``benchmarks/results/``:

    tool: CodeQL
    version: "2.18.4"
    category: Static/taint
    date: 2026-07-30
    manifest_size: 82           # vulnerabilities in the manifest at run time
    blind_copy_commit: 9aa352e  # the commit the tool actually reviewed
    raw_output: raw/codeql.sarif # optional, relative to this file
    notes: >
      Out-of-the-box python-security-extended, no custom taint model.
    findings:
      - id: V01
        claim: "pickle.load on an uploaded artifact in ml/model_loader.py"
      - id: V50
        claim: "check_http_auth compares the bearer token with =="
        # Reported at check_http_auth, which is also decoy D17. It describes
        # the real defect, so it is matched to V50 -- see "score the finding,
        # not the symbol" in SCOREBOARD.md.
      - id: D24
        claim: "X-API-Key-Safe comparison is exploitable"
        # Claims a safe branch is broken -> false positive.
      - id: ~
        claim: "SQL injection in services/registry.py:store_artifact"
        # Matches no entry -> false positive.

``id`` is the manifest entry the finding matches: a ``V`` id when it describes
a real defect, a ``D`` id when it claims a genuinely-safe function is broken,
or ``~`` when it matches nothing. Deciding which is a human judgement made
once, in writing, in the result file. This script only does the arithmetic --
so a disputed score is a disputed line in a committed file, not an argument
about what someone meant months ago.

Usage:
    python benchmarks/score.py                      # every result file
    python benchmarks/score.py results/codeql.yaml  # one
    python benchmarks/score.py --markdown           # scoreboard-ready table
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "benchmarks" / "ground_truth.yaml"
RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"


def load_manifest() -> tuple[set[str], set[str], set[str]]:
    doc = yaml.safe_load(MANIFEST.read_text())
    return ({v["id"] for v in doc.get("vulnerabilities", [])},
            {d["id"] for d in doc.get("decoys", [])},
            {c["id"] for c in doc.get("config_findings", [])})


class Score:
    def __init__(self, path: Path, vulns: set[str], decoys: set[str],
                 config_findings: set[str]):
        doc = yaml.safe_load(path.read_text()) or {}
        self.path = path
        self.tool = doc.get("tool") or path.stem
        self.category = doc.get("category", "?")
        self.notes = doc.get("notes", "")
        self.manifest_size = doc.get("manifest_size")
        self.blind_copy_commit = doc.get("blind_copy_commit")
        self.raw_output = doc.get("raw_output")
        # How the tool was invoked. `single-run` is one invocation over the
        # whole blind copy -- the only shape directly comparable across tools.
        # `partitioned-sweep` splits the app into regions and reviews each
        # separately, which materially helps recall by shrinking the context a
        # reviewer must hold at once; those runs are reported in their own
        # table rather than ranked against single runs. Defaults to
        # single-run so an omitted field can never silently promote a sweep
        # into the primary comparison.
        self.protocol = doc.get("protocol", "single-run")

        self.problems: list[str] = []
        self.found: set[str] = set()          # true positives
        self.config_found: set[str] = set()   # CF ids, scored separately
        self.decoy_fps: list[str] = []        # claimed a safe function is broken
        self.unmatched_fps: list[str] = []    # matched no entry at all

        for i, finding in enumerate(doc.get("findings") or []):
            fid = finding.get("id")
            claim = (finding.get("claim") or "").strip()
            if not claim:
                self.problems.append(f"finding {i} has no `claim:` text")
            if fid is None:
                self.unmatched_fps.append(claim)
            elif fid in vulns:
                if fid in self.found:
                    self.problems.append(
                        f"{fid} claimed more than once -- collapse to one finding")
                self.found.add(fid)
            elif fid in config_findings:
                # CF entries have no source/sink, so they are not part of the
                # taint recall figure -- see SCOREBOARD.md.
                self.config_found.add(fid)
            elif fid in decoys:
                self.decoy_fps.append(f"[{fid}] {claim}")
            else:
                self.problems.append(f"finding {i} references unknown id {fid!r}")

        if self.raw_output and not (path.parent / self.raw_output).exists():
            self.problems.append(f"raw_output {self.raw_output!r} does not exist")

        self.total = len(vulns)
        self.recall = len(self.found) / self.total if self.total else 0.0

    @property
    def false_positives(self) -> int:
        return len(self.decoy_fps) + len(self.unmatched_fps)

    @property
    def stale(self) -> bool:
        return self.manifest_size is not None and self.manifest_size != self.total

    def summary(self) -> str:
        out = [
            f"{self.tool}  ({self.category})",
            f"  recall           {len(self.found)}/{self.total} ({self.recall * 100:.0f}%)",
            f"  decoy FPs        {len(self.decoy_fps)}  "
            f"(claimed a genuinely-safe function is broken)",
            f"  unmatched        {len(self.unmatched_fps)}  "
            f"(reports matching no manifest entry)",
        ]
        if self.config_found:
            out.append(f"  config findings  {len(self.config_found)} "
                       f"({', '.join(sorted(self.config_found))}) -- scored separately")
        if self.blind_copy_commit:
            out.append(f"  reviewed         {self.blind_copy_commit}")
        if not self.raw_output:
            out.append("  ~ no raw_output recorded -- this score cannot be re-derived")
        if self.stale:
            out.append(
                f"  ! run targeted a {self.manifest_size}-entry manifest, scored "
                f"against {self.total}; the {self.total - self.manifest_size} added "
                f"since are credited as missed")
        for p in self.problems:
            out.append(f"  ! {p}")
        return "\n".join(out)


SCOREBOARD = REPO_ROOT / "SCOREBOARD.md"
MARK_START = "<!-- SCOREBOARD:START -->"
MARK_END = "<!-- SCOREBOARD:END -->"

#: Bar width for the ASCII chart, in characters, at 100%.
_BAR_WIDTH = 40


def extract_generated_block(path: Path) -> str | None:
    """The text between the generated-block markers, or None if absent."""
    if not path.exists():
        return None
    text = path.read_text()
    try:
        after = text.split(MARK_START, 1)[1]
        return after.split(MARK_END, 1)[0]
    except IndexError:
        return None


def _table(scores: list["Score"], decoy_total: int) -> list[str]:
    out = [f"| Tool | Category | Recall | Decoy FPs (of {decoy_total}) | Unmatched | Reviewed |",
           "|------|----------|--------|--------------|-----------|----------|"]
    for s in scores:
        out.append(
            f"| {s.tool} | {s.category} | {len(s.found)}/{s.total} "
            f"({s.recall * 100:.0f}%) | {len(s.decoy_fps)} | "
            f"{len(s.unmatched_fps)} | `{s.blind_copy_commit or '?'}` |")
    return out


#: protocol -> short label for the Run column. Kept as a column rather than
#: separate tables: the distinction is real (a partitioned sweep or an
#: LLM-driven pipeline is not the same shape as one deterministic scan) but it
#: is one fact about a row, not a reason for three tables.
_RUN_LABEL = {
    "single-run": "single",
    "agentic-pipeline": "agentic",
    "partitioned-sweep": "sweep",
}


def render_scoreboard(scores: list["Score"], decoy_total: int) -> str:
    """One table, ranked by recall, with the run shape as a column.

    Only tools with a committed result file appear. Numbers with no artifact
    behind them stay out of the ranking entirely -- see SCOREBOARD.md.
    """
    out = ["", "```"]
    for s in scores:
        filled = round(s.recall * _BAR_WIDTH)
        bar = "\u2588" * filled + "\u2591" * (_BAR_WIDTH - filled)
        out.append(f"{s.tool[:30]:30} {bar}  {s.recall * 100:.0f}%")
    out.append("```")
    out.append("")
    out.append(f"| Tool | Run | Category | Recall | Decoy FPs (of {decoy_total}) | Unmatched |")
    out.append("|------|-----|----------|--------|--------------|-----------|")
    for s in scores:
        out.append(
            f"| {s.tool} | {_RUN_LABEL.get(s.protocol, s.protocol)} | {s.category} | "
            f"{len(s.found)}/{s.total} ({s.recall * 100:.0f}%) | "
            f"{len(s.decoy_fps)} | {len(s.unmatched_fps)} |")
    out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", nargs="*", type=Path)
    ap.add_argument("--markdown", action="store_true",
                    help="emit a SCOREBOARD.md-shaped table")
    ap.add_argument("--emit-scoreboard", action="store_true",
                    help="emit the full generated SCOREBOARD.md block (bar "
                         "chart + per-protocol tables) for the region between "
                         "the SCOREBOARD:START/END markers")
    ap.add_argument("--check-scoreboard", action="store_true",
                    help="exit non-zero if SCOREBOARD.md's generated block is "
                         "not what --emit-scoreboard would produce (CI guard "
                         "against the table drifting from results/ again)")
    args = ap.parse_args()

    vulns, decoys, config_findings = load_manifest()
    paths = args.results or sorted(
        p for p in RESULTS_DIR.glob("*.yaml") if not p.name.startswith("_"))
    if not paths:
        print(f"No result files under {RESULTS_DIR.relative_to(REPO_ROOT)}/ -- "
              f"see the format in this script's docstring.", file=sys.stderr)
        return 1

    scores = sorted((Score(p, vulns, decoys, config_findings) for p in paths),
                    key=lambda s: -s.recall)

    if args.emit_scoreboard or args.check_scoreboard:
        block = render_scoreboard(scores, len(decoys))
        if args.emit_scoreboard:
            print(block)
            return 0
        current = extract_generated_block(SCOREBOARD)
        if current is None:
            print(f"{SCOREBOARD.name}: no {MARK_START} / {MARK_END} markers "
                  f"found -- add them around the generated tables.",
                  file=sys.stderr)
            return 1
        if current.strip() != block.strip():
            print(f"{SCOREBOARD.name} is out of date with "
                  f"benchmarks/results/. Regenerate with:\n"
                  f"  python benchmarks/score.py --emit-scoreboard",
                  file=sys.stderr)
            return 1
        print(f"{SCOREBOARD.name} matches benchmarks/results/.")
        return 0

    if args.markdown:
        print(f"| Tool | Category | Recall | Decoy FPs (of {len(decoys)}) | Unmatched |")
        print("|------|----------|--------|--------------|-----------|")
        for s in scores:
            print(f"| {s.tool} | {s.category} | {len(s.found)}/{s.total} "
                  f"({s.recall * 100:.0f}%) | {len(s.decoy_fps)} | "
                  f"{len(s.unmatched_fps)} |")
    else:
        for s in scores:
            print(s.summary())
            print()

    problems = sum(len(s.problems) for s in scores)
    if problems:
        print(f"{problems} problem(s) in the result files above.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Larchway suite (framework-mutation benchmark)

The langfail vulnerabilities ported to a different framework (FastAPI/Starlette,
async) and a different domain (an evaluation and annotation workbench), so a
scanner has to model the framework's request handling, dependency injection,
background work, and response construction rather than recognise a corpus it
has seen. Design and rationale: [ADR 0002](../../../docs/adr/0002-larchway-framework-mutation.md)
(building on [ADR 0001](../../../docs/adr/0001-blinded-mutation-benchmark.md)).

- **Corpus (public):** [`larchway/`](../../../larchway/) at the repo root, a
  runnable vulnerable app with neutral names and no vuln markers.
- **Answer key + PoCs (held out):** `ground_truth.yaml` and `tests/` here are
  git-ignored and released only after a scored run, so a frozen rule set cannot
  be tuned to the set. Same schema and same vulnerability ids as
  `benchmarks/ground_truth.yaml`, plus a `mutation:` block per entry and the
  suite's kill chains.
- **v1 scope:** the agent/assistant tier of langfail is not ported. The key's
  `not_ported:` list names those ids; they are left out of the recall
  denominator, so compare larchway recall with langfail per id, not as a
  headline percentage.

## Running (once the key is present locally)

```bash
python benchmarks/check_ground_truth.py --suite larchway      # answer key resolves against larchway/
python -m pytest benchmarks/suites/larchway/tests             # PoCs prove exploitability
python scripts/export_blind_copy.py <dest> --suite larchway   # the blind copy a reviewer gets
python benchmarks/score.py --suite larchway results/<tool>.yaml   # score a tool's findings
```

Result files go in `results/` (git-ignored) and follow the format in
`benchmarks/score.py`'s docstring. The review prompt is
[`scan_prompt.md`](scan_prompt.md). Larchway does not publish to the public
`SCOREBOARD.md`.

**Adjudicate by hand.** Map every finding to a `V`, `D`, or `~` id yourself.
Symbol-anchored auto-matching undercounts findings on a mutated corpus, because
a correct report often anchors at a different hop than the key does.

## Chain scoring

Besides recall and decoy false positives, `score.py` reports each chain in the
key as **full** (every member found), **partial** (n of m), or **none**, plus a
summary line. Kill chains also have a broken-chain twin (the same path with one
link fixed); a tool that flags that twin's decoy is reported as over-claiming
the chain.

## The mutations

ADR 0001's six (rename, rewrap APIs, relocate sources/sinks, rewrite guards, a
safe twin for every mutation, hold out the key) plus framework-level axes:
typed sources, dependency-injected receivers, async and deferred hops, guards
in the framework, class dispatch, model round-trips, response-class sinks, and
framework-native safe twins. Full detail in ADR 0002.

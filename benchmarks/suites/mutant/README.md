# Mutant suite (blinded mutation benchmark)

The same vulnerabilities as the `langfail` suite, mutated so a scanner cannot
recognise them by name, path, API call, or guard shape: it has to re-derive each
finding from data flow. Design and rationale: [ADR 0001](../../../docs/adr/0001-blinded-mutation-benchmark.md).

- **Corpus (public):** [`modelbay/`](../../../modelbay/) at the repo root, a
  runnable vulnerable app with neutral names and no vuln markers.
- **Answer key + PoCs (held out):** `ground_truth.yaml` and `tests/` here are
  git-ignored and released only after a scored run, so a frozen rule set cannot
  be tuned to the set. Same schema and same vulnerability ids as
  `benchmarks/ground_truth.yaml`, plus a `mutation:` block per entry recording how
  it was derived from its langfail original.

## Running (once the key is present locally)

```bash
python benchmarks/check_ground_truth.py --suite mutant     # answer key resolves against modelbay/
python -m pytest benchmarks/suites/mutant/tests            # PoCs prove exploitability
python benchmarks/score.py --suite mutant results/<tool>.yaml   # score a tool's findings
```

Result files go in `results/` and follow the format in `benchmarks/score.py`'s
docstring. The mutant suite does not publish to the public `SCOREBOARD.md`.

## The six mutations

Rename · rewrap APIs · relocate sources/sinks · rewrite guards into equivalent
forms · a safe twin for every mutation · hold out the answer key. Full detail in
the ADR.

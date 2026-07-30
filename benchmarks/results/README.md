# Benchmark results

One YAML file per run, plus its raw output. `python benchmarks/score.py`
reads every file here and prints the scores; `--markdown` emits a table you
can paste into [SCOREBOARD.md](../../SCOREBOARD.md).

**This directory is why the scores on SCOREBOARD.md are marked unreliable.**
It did not exist when they were collected. Nothing recorded which finding a
tool matched to which manifest entry, so none of those numbers can be
re-derived, re-scored after a manifest change, or checked by anyone else. Any
new run belongs here.

## Adding a run

1. Export a blind copy and note the commit it came from:

   ```bash
   git rev-parse --short HEAD
   python scripts/export_blind_copy.py /tmp/langfail-blind
   ```

   The exporter refuses to produce a copy containing a spoiler. If it exits
   non-zero, fix the source it points at — do not work around it.

2. Run the tool. Save whatever it produces verbatim under `raw/`.

3. Write `<tool>.yaml` (copy `_template.yaml`) and map each reported finding
   to a manifest id. Two rules that decide most of the hard cases:

   - **Score the finding, not the symbol.** Three decoys share a function
     with a real entry (D02/D17/D24). If the report describes the real
     defect, match it to the `V` id. If it claims the safe branch is broken,
     match it to the `D` id, which counts as a false positive.
   - **One line per manifest entry.** If a tool reports the same bug four
     times, that is one finding. If it reports four different bugs in one
     function, that is four.

4. Check it:

   ```bash
   python benchmarks/score.py results/<tool>.yaml
   ```

   It fails on unknown ids, duplicate ids, missing claim text, and a
   `raw_output` path that does not exist. It warns when a run targeted an
   older, smaller manifest — those entries are credited as missed, which is
   the conservative call, so a re-run is always worth more than a back-fill.

## What to write in `claim`

Enough that someone else can check the mapping without the raw output in
front of them. `"pickle.load on an uploaded artifact in ml/model_loader.py"`
is reviewable. `"deserialization issue"` is not.

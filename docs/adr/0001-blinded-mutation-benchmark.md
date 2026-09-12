# ADR 0001: Blinded mutation benchmark as a second suite

Status: accepted
Date: 2026-09-07

## Context

The `langfail` corpus and its `ground_truth.yaml` have been public long enough
that a scanner can score well by recognising *this* codebase rather than by
analysing it: the symbol names, file layout, API calls, and guard shapes are all
memorisable. A high recall number no longer cleanly separates "understands the
vulnerability class" from "has seen langfail before."

We want a second benchmark that holds the vulnerability *semantics* fixed while
changing everything a memoriser keys on, so a tool has to re-derive each finding
from data flow, not from a remembered fingerprint. It must sit alongside the
original, be scored by the same tooling, and be runnable so exploitability stays
proven, not asserted.

## Decision

Add a **mutant suite**: a parallel vulnerable app (`modelbay/`) carrying the same
vulnerabilities as `langfail/`, each mutated across six axes, plus a safe twin
for every mutation. The answer key is held out of the public tree.

### Suites, not forks

Scoring becomes suite-addressable. `benchmarks/score.py --suite <name>` and
`benchmarks/check_ground_truth.py --suite <name>` select which manifest (and, for
scoring, which results dir) to read. The default suite is `langfail`, pointing at
the existing `benchmarks/ground_truth.yaml` and `benchmarks/results/` in place, so
nothing about the original benchmark moves or changes. The `mutant` suite points
at `benchmarks/suites/mutant/`.

The mutant manifest reuses the langfail schema unchanged (`vulnerabilities`,
`decoys`, `config_findings`, ...) and keeps the **same vulnerability ids** (V03 in
the mutant suite is the mutation of V03 in langfail). Identical ids make recall
comparable per vulnerability across the two suites, and mean `score.py` scores the
mutant suite with no change to its arithmetic.

### The six mutations

Every planted vulnerability is transformed so its surface differs while its
exploitability is preserved:

1. **Rename** functions, models, keys, variables, env prefixes, the package
   itself (`langfail` -> `modelbay`). Defeats name-keyed recall.
2. **Rewrap APIs** in equivalent shims: the dangerous call reaches the same
   primitive through a wrapper of a different name (e.g. `pickle.load` behind a
   `restore_object` helper, `subprocess ... shell=True` behind a `run_shell`
   utility). Defeats signature-keyed rules that match the library call directly.
3. **Relocate** sources and sinks to different files, layers, and (where the
   original did not) process boundaries, so a memorised source->sink path does not
   transfer.
4. **Rewrite guards** into logically equivalent forms: the broken check keeps its
   exact bypass but a different shape (a single-pass `str.replace` traversal strip
   becomes a regex sub with the same `....//` gap; an `endswith` host allow-list
   becomes an `in`-substring test with the same suffix bypass).
5. **Safe variant for every mutation.** Each mutated vulnerability ships a decoy:
   the same mutated surface with the flaw actually fixed. Flagging it is a
   measurable false positive, exactly as in langfail. This preserves the precision
   axis under mutation.
6. **Hide the mutation set.** The answer key is held out (below).

Which axes apply to a given vulnerability is recorded per entry, so the set is
auditable and reproducible rather than ad hoc.

### Mutation provenance

Each mutant manifest entry carries a `mutation:` block recording how it was
derived from its langfail original:

```yaml
mutation:
  origin: V03                       # the langfail vuln this mutates
  transforms: [rename, rewrap, relocate, guard-rewrite]
  renames: {get_blob: fetch_blob, read_artifact: load_blob, sanitize_path: normalize_name}
  wrappers: []                      # original API -> shim used
  relocation: {sink_from: langfail/services/registry.py, sink_to: modelbay/store/blobs.py}
  guard_rewrite: {from: "str.replace '../' strip", to: "regex sub, same ....// gap"}
  safe_variant: D01                 # the decoy id that is this vuln's safe twin
```

This block is the map from mutant back to original. It lives only in the held-out
manifest, never in `modelbay/` source (the corpus must contain no vuln markers,
the same rule langfail follows).

### Held-out answer key

Per the blinding requirement, the public tree carries only the mutated *app*. The
answer key and proofs are git-ignored and released after a scored run, so a tool
cannot be tuned to the set while its rules are frozen:

- **Public / committed:** `modelbay/` (the corpus), `benchmarks/suites/mutant/README.md`,
  the harness changes, this ADR. The corpus is a vulnerable app with neutral
  names and no markers; that it is a benchmark fixture is not itself secret (nor
  is it for langfail).
- **Held out / git-ignored, local until release:**
  `benchmarks/suites/mutant/ground_truth.yaml` (answer key with `mutation:` blocks)
  and `benchmarks/suites/mutant/tests/` (the runnable PoCs). Committing the PoCs
  would enumerate every sink, so they are held out with the key.

The existing `blind_copy_commit` field in the result format already records the
commit a tool reviewed; the mutant suite adds name/path/API blinding on top of that
commit-freeze, so even a tool that memorised langfail gets no transfer.

## Consequences

- The original benchmark is untouched: same paths, same numbers, same commands.
  `score.py` / `check_ground_truth.py` with no flag behave exactly as before.
- A tool run against both suites yields a memorisation-vs-analysis delta per
  vulnerability id: a large langfail-minus-mutant recall gap on an id is evidence
  of fingerprinting rather than analysis.
- The mutant corpus is authored once and then frozen; freezing is what makes the
  held-out key meaningful. It is a one-time artifact, not a generator, so it stays
  plain readable source (no build step, matching the repo's minimum-machinery
  preference).
- Cost: the corpus is a second app to keep runnable. Every mutated vulnerability
  keeps a PoC, so `check_ground_truth.py --suite mutant` and the held-out test
  suite are the guardrails against the mutation silently breaking exploitability.
- The mutant suite does not publish to the public `SCOREBOARD.md`/`README.md`
  chart; those stay langfail-only while the key is held out.

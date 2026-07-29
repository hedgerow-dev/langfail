# Security Policy

**Docs:** [README](README.md) · [Architecture](ARCHITECTURE.md) · [Scoreboard](SCOREBOARD.md)

## This repository is intentionally vulnerable

Langfail is a security **benchmark target**. Every vulnerability under
`langfail/` and `deploy/` was planted deliberately, documented in
[`benchmarks/ground_truth.yaml`](benchmarks/ground_truth.yaml), and proved with
a PoC test. **Please don't report them** — they're the product, not the defect.

Don't deploy this, don't expose it to a network, don't run it anywhere you care
about. See the warning in [`README.md`](README.md).

## What to report

Open a GitHub issue for problems in the **benchmark tooling**:

- the answer-key or scoring format (`benchmarks/ground_truth.yaml`,
  `benchmarks/check_ground_truth.py`)
- exploit proofs or decoy tests that are broken, flaky, or mislabeled
- a planted vulnerability reachable in a way the ground truth doesn't
  document — e.g. a much simpler exploit path that makes the entry misleading
- CI or packaging issues

## Ground rules for PoCs

A new planted vulnerability needs three things: a runnable proof under `tests/`,
a ground-truth entry, and a precision decoy (a safe look-alike) — matching the
conventions already in `benchmarks/ground_truth.yaml`.

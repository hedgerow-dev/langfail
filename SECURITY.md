# Security Policy

**Docs:** [README](README.md) · [Architecture](ARCHITECTURE.md) · [Scoreboard](SCOREBOARD.md)

## This repository is intentionally vulnerable

Langfail is a **security benchmark target**. Every vulnerability in the
application code under `langfail/` and `deploy/` is planted on purpose, documented
in the answer key at [`benchmarks/ground_truth.yaml`](benchmarks/ground_truth.yaml),
and covered by a proof-of-concept test. **Please do not report these** — they
are the product, not a defect.

Do not deploy this application, expose it to a network, or run it anywhere you
care about. See the warning in [`README.md`](README.md).

## What to report

Please open a GitHub issue for problems in the **benchmark tooling** itself:

- the scoring/answer-key format (`benchmarks/ground_truth.yaml`,
  `benchmarks/check_ground_truth.py`),
- exploit proofs or decoy tests that are broken, flaky, or mislabeled,
- a planted vulnerability that is reachable in a way the ground truth does not
  document (e.g. a much simpler exploit path that makes the entry misleading),
- CI or packaging issues.

## Ground rules for PoCs

If you contribute a new planted vulnerability, it must come with a runnable
proof under `tests/`, a ground-truth entry, and a precision decoy (a safe
look-alike) — matching the conventions in `benchmarks/ground_truth.yaml`.

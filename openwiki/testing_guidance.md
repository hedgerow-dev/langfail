# Langfail Testing Guidance

Running benchmarks and exploit validations.

## Labeled Answer Key
The ground truth of all vulnerabilities is recorded in:
* `benchmarks/ground_truth.yaml`

This file details every exploit path, mapping the start line, taint flow nodes, and end sink.

## Exploit Assertions
We run pytest to verify that all exploit paths are functional and that security tools block them:
```bash
PYTHONPATH=. pytest
```

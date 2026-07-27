# Langfail Source Map

Source code directory index:

* `dvml/api/`: Flask API blueprints (vulnerability sources).
* `dvml/services/`: Core logic and SQL/file sinks.
* `dvml/ml/`: Model file loader, metrics, and dataset extractors.
* `dvml/workers/`: SQLite-backed job queue and task drainers.
* `dvml/agent/`: LLM agent loop and tool definitions.
* `exploits/`: Executable exploit chains.
* `benchmarks/ground_truth.yaml`: Taint flow answers.

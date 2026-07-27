# Langfail Source Map

Source code directory index:

* `langfail/api/`: Flask API blueprints (vulnerability sources).
* `langfail/services/`: Core logic and SQL/file sinks.
* `langfail/ml/`: Model file loader, metrics, and dataset extractors.
* `langfail/workers/`: SQLite-backed job queue and task drainers.
* `langfail/agent/`: LLM agent loop and tool definitions.
* `exploits/`: Executable exploit chains.
* `benchmarks/ground_truth.yaml`: Taint flow answers.

# Langfail Architecture Overview

Langfail is designed as a mock MLOps platform featuring an inference service, a model registry, and an LLM-powered assistant.

## Data-Flow Architecture

```
Taint Source (Flask Ingress)  ──>  Business Logic Service  ──>  Queue Worker  ──>  Exploitable Sink
(langfail/api/blueprint.py)            (langfail/services/)              (Job queue)      (subprocess/pickle)
```

## Description of Components

1. **Flask API Blueprints (`langfail/api/`):** Ingress controllers representing the user surface. Taint sources originate from query params, request bodies, and files.
2. **Business Services (`langfail/services/`):** Houses MLOps logic, containing sinks such as raw SQL queries, file read/write paths, and template formatters.
3. **Queue Workers (`langfail/workers/`):** Reads task records from SQLite and executes them asynchronously. Taint propagates across processes through database roundtrips.
4. **LLM Assistant Loop (`langfail/agent/`):** Simple agent loop interacting with users. Serves as a prompt injection surface.

# Langfail Integrations

Integrations with external components.

## 1. Pluggable Local LLM Backends
* **Stub Backend (default):** Offline, deterministic mock engine used for testing.
* **Ollama Backend:** Connects to a local Ollama server running `llama3.1` or `qwen2.5-coder`.

## 2. MCP Server Protocol
Exposes MLOps tools directly to other AI agents over stdio or HTTP, allowing agents to execute functions and access workspace details.

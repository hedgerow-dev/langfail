# Langfail Operations Guide

Operating Langfail.

## Global Environment Variables
* `DVML_JWT_SECRET`: Secret token used to sign authentication cookies.
* `DVML_LLM_BACKEND`: Local assistant LLM type (`stub`, `ollama`).
* `DVML_LLM_OLLAMA_URL`: Local Ollama server address.

## Model Forge MCP Server
To expose Langfail tools via Model Context Protocol (MCP):
```bash
# Start MCP server over stdio
flask --app dvml mcp-serve
# Start MCP server over SSE/HTTP
flask --app dvml mcp-serve-http
```

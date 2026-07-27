# Langfail Quick Start Guide

Welcome to the OpenWiki for Langfail (Damn Vulnerable AI:ML app). Langfail is a deliberately vulnerable MLOps dashboard built with Flask + SQLite.

## Project Purpose
Langfail serves as a security benchmark target for static taint analyzers and agentic vulnerability hunt tools. It contains **41 planted vulnerabilities** (plus precision decoys) spanning from simple single-hop vulnerabilities to multi-hop blind SSRF, agent memory poisoning, and text-to-SQL prompt injection.

## Wiki Navigation
* **[Architecture Overview](architecture.md):** Model layout and cross-taint design.
* **[Development Workflows](workflows.md):** Running Flask services and executing exploits.
* **[Domain Concepts](domain_concepts.md):** Database roundtrips and agent tool exposure.
* **[Operations Guide](operations.md):** Startup variables and local Ollama hooks.
* **[Integrations](integrations.md):** Pluggable backends and MCP tools.
* **[Testing Guidance](testing_guidance.md):** Labeled answer keys and pytest suites.
* **[Source Map](source_map.md):** Project folders list.

## Real Repository Documentation

These links connect directly to the pre-existing, source-of-truth documentation files in this repository:
* [ARCHITECTURE.md](../ARCHITECTURE.md)
* [README.md](../README.md)
* [SCOREBOARD.md](../SCOREBOARD.md)

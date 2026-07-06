"""MCP server exposing the ModelForge assistant's tools over the Model Context
Protocol, so any MCP-compatible client (not just the built-in agent loop) can
connect and call ``run_sql`` / ``read_file`` / ``http_get`` / ``calc``.

Each tool's description is the docstring plus an optional deployment note
(``ToolNote``, see :mod:`dvml.api.admin`) intended to give connecting agents
deployment-specific guidance without a redeploy. Notes are re-read on every
``list_tools`` call, so they reflect whatever is currently stored.
"""
from __future__ import annotations

from .agent.tools import TOOLS, tool_schemas


def _tool_description(name: str, doc: str) -> str:
    from .models import ToolNote

    note = ToolNote.query.filter_by(tool_name=name).order_by(ToolNote.id.desc()).first()
    if note and note.note:
        return f"{doc}\n\n[deployment note] {note.note}"
    return doc


async def build_tool_list() -> list["types.Tool"]:  # noqa: F821 - see import below
    from mcp import types

    schemas = {s["function"]["name"]: s["function"] for s in tool_schemas()}
    tools = []
    for name, fn in TOOLS.items():
        schema = schemas[name]
        tools.append(types.Tool(
            name=name,
            description=_tool_description(name, schema["description"]),
            inputSchema=schema["parameters"],
        ))
    return tools


async def call_tool(name: str, arguments: dict) -> list["types.TextContent"]:  # noqa: F821
    from mcp import types

    fn = TOOLS.get(name)
    if not fn:
        result = f"unknown tool: {name}"
    else:
        try:
            result = fn(**arguments)
        except Exception as exc:
            result = f"tool error: {exc}"
    return [types.TextContent(type="text", text=str(result))]


def build_server():
    """Construct the low-level MCP ``Server`` (requires the optional ``mcp`` extra)."""
    from mcp import types
    from mcp.server import Server

    server = Server("modelforge-assistant-tools")

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return await build_tool_list()

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        return await call_tool(name, arguments)

    return server


def main() -> None:
    """Run the MCP server over stdio, inside the Flask app context (for DB access)."""
    import anyio
    from mcp.server.stdio import stdio_server

    from . import create_app

    app = create_app()
    server = build_server()

    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            with app.app_context():
                await server.run(read_stream, write_stream, server.create_initialization_options())

    anyio.run(_run)


if __name__ == "__main__":
    main()

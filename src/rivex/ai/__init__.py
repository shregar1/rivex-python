"""Rivex AI-native features — MCP server, agent framework, LLM streaming.

Integrates the Model Context Protocol (MCP) with  high-performance
routing, provides an agent runner with tool calling, and SSE streaming
helpers for LLM responses.

Submodules:
    - :mod:`rivex.ai.mcp_server` — MCP server that mounts on a Rivex app
    - :mod:`rivex.ai.providers` — LLM provider abstraction (OpenAI, Anthropic)
    - :mod:`rivex.ai.agent` — Agent with tools, memory, streaming
    - :mod:`rivex.ai.streaming` — SSE streaming for chat completions

Quick start::

    from rivex import Rivex
    from rivex.ai import MCPServer, Agent

    app = Rivex()

    # 1. MCP server — expose tools to Claude Desktop / Cursor
    mcp = MCPServer(app, mount="/mcp")

    @mcp.tool()
    def search(query: str, limit: int = 10) -> list[dict]:
        \"\"\"Search the knowledge base.\"\"\"
        return db.search(query, limit)

    @mcp.resource("config://app")
    def app_config() -> str:
        return json.dumps({"version": "1.0", "features": [...]})

    # 2. Agent — tool-calling LLM agent
    agent = Agent(
        name="assistant",
        system_prompt="You help users find information.",
        model="gpt-4o",
        tools=[search],
    )

    @app.post("/chat")
    async def chat(message: str):
        response = await agent.run(message)
        return {"response": response}

    @app.get("/chat/stream")
    async def chat_stream(message: str):
        async for token in agent.stream(message):
            yield token

Requires:
    - ``mcp`` package (``pip install mcp``) for MCP server
    - ``openai`` package (``pip install openai``) for OpenAI provider
    - ``anthropic`` package (``pip install anthropic``) for Anthropic provider
"""

from __future__ import annotations

from rivex.ai.agent import Agent
from rivex.ai.mcp_server import MCPServer
from rivex.ai.providers import AnthropicProvider, OpenAIProvider, Provider
from rivex.ai.streaming import stream_completion

__all__ = [
    "Agent",
    "AnthropicProvider",
    "MCPServer",
    "OpenAIProvider",
    "Provider",
    "stream_completion",
]

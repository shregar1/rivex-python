"""Tests for rivex.ai — MCP server, agent, providers, streaming."""

from __future__ import annotations

import pytest

from rivex import Rivex
from rivex.ai import Agent, MCPServer, OpenAIProvider, Provider


@pytest.fixture
def app():
    return Rivex(docs_url=None, redoc_url=None, landing_page=False, openapi_url=None)


# ──────────────────────────────────────────────────────────────────────
# MCP Server
# ──────────────────────────────────────────────────────────────────────


class TestMCPServer:
    def test_mcp_server_creation(self, app):
        mcp = MCPServer(app, mount="/mcp", name="test-server")
        assert mcp._name == "test-server"
        assert mcp._mount == "/mcp"

    def test_mcp_registers_routes(self, app):
        MCPServer(app, mount="/mcp")
        # POST /mcp for JSON-RPC
        # GET /mcp for discovery
        post_routes = [r for r in app._routes if r.path == "/mcp" and r.method == "POST"]
        get_routes = [r for r in app._routes if r.path == "/mcp" and r.method == "GET"]
        assert len(post_routes) == 1
        assert len(get_routes) == 1

    def test_tool_registration(self, app):
        mcp = MCPServer(app)

        @mcp.tool()
        def search(query: str, limit: int = 10) -> list:
            """Search the database."""
            return [f"result_{query}_{i}" for i in range(limit)]

        assert "search" in mcp._tools
        schema = mcp._tools["search"]["schema"]
        assert schema["name"] == "search"
        assert schema["description"] == "Search the database."
        assert "query" in schema["inputSchema"]["properties"]
        assert schema["inputSchema"]["properties"]["query"]["type"] == "string"
        assert schema["inputSchema"]["properties"]["limit"]["type"] == "integer"
        assert "query" in schema["inputSchema"]["required"]
        assert "limit" not in schema["inputSchema"]["required"]

    def test_resource_registration(self, app):
        mcp = MCPServer(app)

        @mcp.resource("db://{table}")
        def table_data(table: str) -> str:
            """Export table data."""
            return f"data from {table}"

        assert "db://{table}" in mcp._resources
        schema = mcp._resources["db://{table}"]["schema"]
        assert schema["uri"] == "db://{table}"
        assert schema["name"] == "table_data"
        assert schema["description"] == "Export table data."

    def test_prompt_registration(self, app):
        mcp = MCPServer(app)

        @mcp.prompt()
        def code_review(language: str, code: str) -> str:
            """Review code."""
            return f"Reviewing {language}:\n{code}"

        assert "code_review" in mcp._prompts
        schema = mcp._prompts["code_review"]["schema"]
        assert schema["name"] == "code_review"
        assert {"name": "language", "required": True} in schema["arguments"]
        assert {"name": "code", "required": True} in schema["arguments"]

    def test_tool_execution(self, app):
        mcp = MCPServer(app)

        @mcp.tool()
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        result = mcp._call_tool({"name": "add", "arguments": {"a": 3, "b": 4}})
        assert result["content"][0]["text"] == "7"

    def test_resource_reading(self, app):
        mcp = MCPServer(app)

        @mcp.resource("config://{key}")
        def get_config(key: str) -> str:
            return f"value_for_{key}"

        result = mcp._read_resource({"uri": "config:///debug"})
        assert "value_for_/debug" in result["contents"][0]["text"]

    def test_prompt_rendering(self, app):
        mcp = MCPServer(app)

        @mcp.prompt()
        def summarize(text: str) -> str:
            """Summarize text."""
            return f"Summary of: {text}"

        result = mcp._get_prompt({"name": "summarize", "arguments": {"text": "hello"}})
        assert "Summary of: hello" in result["messages"][0]["content"]["text"]

    def test_initialize_handshake(self, app):
        mcp = MCPServer(app, name="my-server", version="2.0.0")
        result = mcp._dispatch("initialize", {})
        assert result["serverInfo"]["name"] == "my-server"
        assert result["serverInfo"]["version"] == "2.0.0"
        assert "protocolVersion" in result

    def test_list_tools(self, app):
        mcp = MCPServer(app)

        @mcp.tool()
        def foo(x: int) -> int:
            """Foo function."""
            return x

        result = mcp._dispatch("tools/list", {})
        assert len(result["tools"]) == 1
        assert result["tools"][0]["name"] == "foo"

    def test_list_resources(self, app):
        mcp = MCPServer(app)

        @mcp.resource("file://{name}")
        def read_file(name: str) -> str:
            return f"content of {name}"

        result = mcp._dispatch("resources/list", {})
        assert len(result["resources"]) == 1

    def test_list_prompts(self, app):
        mcp = MCPServer(app)

        @mcp.prompt()
        def greet(name: str) -> str:
            """Greet."""
            return f"Hello {name}"

        result = mcp._dispatch("prompts/list", {})
        assert len(result["prompts"]) == 1

    def test_uri_matching(self):
        # Simple param
        match = MCPServer._match_uri("db://{table}", "db:///users")
        assert match == {"table": "/users"}

        match = MCPServer._match_uri("db://{table}", "db:///orders")
        assert match == {"table": "/orders"}

        # No match
        match = MCPServer._match_uri("db://{table}", "http:///users")
        assert match is None

        # Static URI
        match = MCPServer._match_uri("config://app", "config://app")
        assert match == {}


# ──────────────────────────────────────────────────────────────────────
# Agent
# ──────────────────────────────────────────────────────────────────────


class MockProvider(Provider):
    """Mock provider for testing — returns canned responses."""

    def __init__(self, responses: list[str] | None = None):
        self._responses = responses or ["Mock response"]
        self._call_count = 0

    @property
    def name(self) -> str:
        return "mock"

    async def complete(self, messages, **kwargs):
        return self._responses[min(self._call_count, len(self._responses) - 1)]

    async def stream(self, messages, **kwargs):
        for token in ["Hello", " ", "world", "!"]:
            yield token

    async def complete_with_tools(self, messages, tools, **kwargs):
        # First call: no tool calls
        return {"content": self._responses[0], "tool_calls": []}


class TestAgent:
    def test_agent_creation(self):
        agent = Agent(
            name="test",
            system_prompt="You are a test agent.",
            provider=MockProvider(),
        )
        assert agent.name == "test"
        assert agent.system_prompt == "You are a test agent."

    def test_agent_with_string_provider(self):
        agent = Agent(provider="gpt-4o")
        assert isinstance(agent.provider, OpenAIProvider)
        assert agent.provider.model == "gpt-4o"

    @pytest.mark.asyncio
    async def test_agent_run_simple(self):
        agent = Agent(provider=MockProvider(["Hello!"]))
        result = await agent.run("Hi")
        assert result == "Hello!"

    @pytest.mark.asyncio
    async def test_agent_memory(self):
        agent = Agent(provider=MockProvider(["Response 1"]), memory=True)
        await agent.run("message 1")
        assert len(agent._memory) == 2  # user + assistant

    @pytest.mark.asyncio
    async def test_agent_no_memory(self):
        agent = Agent(provider=MockProvider(["Response 1"]), memory=False)
        await agent.run("message 1")
        assert len(agent._memory) == 0

    def test_agent_clear_memory(self):
        agent = Agent(provider=MockProvider())
        agent._memory = [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]
        agent.clear_memory()
        assert len(agent._memory) == 0

    @pytest.mark.asyncio
    async def test_agent_stream(self):
        agent = Agent(provider=MockProvider())
        tokens = []
        async for token in agent.stream("Hi"):
            tokens.append(token)
        assert tokens == ["Hello", " ", "world", "!"]

    def test_tool_definitions_built(self):
        def search(query: str, limit: int = 10) -> list:
            """Search for things."""
            return []

        agent = Agent(provider=MockProvider(), tools=[search])
        defs = agent._build_tool_defs()
        assert len(defs) == 1
        assert defs[0]["name"] == "search"
        assert defs[0]["description"] == "Search for things."
        assert defs[0]["parameters"]["properties"]["query"]["type"] == "string"
        assert defs[0]["parameters"]["properties"]["limit"]["type"] == "integer"

    def test_tool_execution(self):
        def add(a: int, b: int) -> int:
            return a + b

        agent = Agent(provider=MockProvider(), tools=[add])
        result = agent._execute_tool("add", {"a": 5, "b": 3})
        assert result == "8"

    def test_tool_not_found(self):
        agent = Agent(provider=MockProvider(), tools=[])
        result = agent._execute_tool("nonexistent", {})
        assert "not found" in result


# ──────────────────────────────────────────────────────────────────────
# Providers
# ──────────────────────────────────────────────────────────────────────


class TestProviders:
    def test_openai_provider_creation(self):
        provider = OpenAIProvider(model="gpt-4o", api_key="test-key")
        assert provider.model == "gpt-4o"
        assert provider.api_key == "test-key"
        assert provider.name == "openai"

    def test_openai_provider_env_key(self):
        import os

        old = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "env-key"
        try:
            provider = OpenAIProvider()
            assert provider.api_key == "env-key"
        finally:
            if old is not None:
                os.environ["OPENAI_API_KEY"] = old
            else:
                del os.environ["OPENAI_API_KEY"]

    def test_openai_provider_custom_base_url(self):
        provider = OpenAIProvider(base_url="https://custom.api.com/v1")
        assert provider.base_url == "https://custom.api.com/v1"

    def test_anthropic_provider_creation(self):
        from rivex.ai import AnthropicProvider

        provider = AnthropicProvider(model="claude-sonnet-4-20250514", api_key="test-key")
        assert provider.model == "claude-sonnet-4-20250514"
        assert provider.api_key == "test-key"
        assert provider.name == "anthropic"

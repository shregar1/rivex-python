# Rivex AI — MCP Server, Agent Framework, LLM Streaming

Rivex provides first-class AI-native features, integrating the Model Context
Protocol (MCP), an agent runner with tool calling, and SSE streaming for LLM
responses — all wired into  high-performance routing.

## Quick Start

```python
from rivex import Rivex
from rivex.ai import MCPServer, Agent, OpenAIProvider

app = Rivex()

# ── 1. MCP Server — expose tools to Claude Desktop / Cursor ──
mcp = MCPServer(app, mount="/mcp")

@mcp.tool()
def search(query: str, limit: int = 10) -> list:
    """Search the knowledge base."""
    return db.search(query, limit)

@mcp.resource("config://app")
def app_config() -> str:
    """Get application configuration."""
    return json.dumps({"version": "1.0"})

@mcp.prompt()
def code_review(language: str, code: str) -> str:
    """Generate a code review prompt."""
    return f"Review this {language} code:\n{code}"

# ── 2. Agent — LLM with tool calling ──
agent = Agent(
    name="assistant",
    system_prompt="You help users find information.",
    provider=OpenAIProvider(model="gpt-4o"),
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

app.run()
```

## MCP Server

The Model Context Protocol (MCP) lets AI clients (Claude Desktop, Cursor,
Windsurf) discover and call tools defined in your app.

### Registering Tools

```python
@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a math expression."""
    return str(safe_eval(expression))
```

Type hints become the JSON Schema. The docstring becomes the description.
Claude sees this tool and can call it automatically.

### Registering Resources

```python
@mcp.resource("db://{table}")
def table_data(table: str) -> str:
    """Export a database table."""
    return db.export_csv(table)
```

Resources are URI-templated data sources. The AI client reads them
on-demand via `resources/read`.

### Registering Prompts

```python
@mcp.prompt()
def summarize(text: str, max_words: int = 100) -> str:
    """Summarize text concisely."""
    return f"Summarize in {max_words} words: {text}"
```

Prompts are pre-defined templates users can invoke via slash commands
in the AI client.

### Connecting Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "rivex": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

## Agent Framework

The `Agent` class provides a high-level LLM agent with:

- **Tool calling** (function calling via OpenAI/Anthropic API)
- **Conversation memory** (persists across calls)
- **Streaming** (token-by-token via async generator)
- **Multi-provider** (OpenAI, Anthropic, or custom)

```python
from rivex.ai import Agent, OpenAIProvider

agent = Agent(
    name="research-assistant",
    system_prompt="You are a meticulous research assistant.",
    provider=OpenAIProvider(model="gpt-4o"),
    tools=[search_db, calculate, fetch_url],
    max_iterations=5,
)

# Non-streaming
result = await agent.run("What's the GDP of Japan?")

# Streaming
async for token in agent.stream("Explain quantum entanglement"):
    print(token, end="", flush=True)
```

### Tool Definition

Tools are regular Python functions. Type hints and docstrings are
automatically converted to the LLM's function-calling schema:

```python
def search_db(query: str, limit: int = 10) -> list[dict]:
    """Search the database for matching records.

    Args:
        query: Search query string
        limit: Maximum number of results (default 10)
    """
    return db.search(query, limit)

agent = Agent(tools=[search_db], provider="gpt-4o")
```

### Memory Management

```python
agent = Agent(provider="gpt-4o", memory=True)

# First call — no memory
await agent.run("My name is Alice")

# Second call — remembers the name
await agent.run("What's my name?")  # => "Your name is Alice."

# Clear memory
agent.clear_memory()
```

## LLM Providers

### OpenAI

```python
from rivex.ai import OpenAIProvider

provider = OpenAIProvider(
    model="gpt-4o",
    api_key="sk-...",  # or set OPENAI_API_KEY env var
)
```

### Anthropic

```python
from rivex.ai import AnthropicProvider

provider = AnthropicProvider(
    model="claude-sonnet-4-20250514",
    api_key="sk-ant-...",  # or set ANTHROPIC_API_KEY env var
)
```

### Custom Provider

Implement the `Provider` abstract class:

```python
from rivex.ai.providers import Provider

class MyProvider(Provider):
    @property
    def name(self) -> str:
        return "custom"

    async def complete(self, messages, **kwargs) -> str:
        # Call your LLM API
        ...

    async def stream(self, messages, **kwargs):
        # Yield tokens
        yield "token1"
```

## SSE Streaming

For raw LLM streaming (without the Agent loop):

```python
from rivex.ai import stream_completion, OpenAIProvider

provider = OpenAIProvider(model="gpt-4o")

@app.post("/complete")
async def complete(body: dict):
    return stream_completion(
        provider,
        messages=body["messages"],
        system="You are a helpful assistant.",
    )
```

The client receives Server-Sent Events:

```
data: {"content": "Hello"}

data: {"content": " there"}

data: {"content": "!"}

data: [DONE]
```

## Installation

```bash
# Core (MCP server + agent + streaming)
pip install rivex

# LLM providers (install what you need)
pip install openai       # for OpenAIProvider
pip install anthropic    # for AnthropicProvider
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│ Claude Desktop / Cursor / Windsurf              │
│         (MCP Client)                            │
└──────────────────┬──────────────────────────────┘
                   │ JSON-RPC over HTTP
                   ▼
┌─────────────────────────────────────────────────┐
│ Rivex App                                       │
│  ├── MCPServer (/mcp endpoint)                  │
│  │     ├── tools/list → [{name, schema}]        │
│  │     ├── tools/call → execute Python function │
│  │     ├── resources/list → [{uri, ...}]        │
│  │     └── prompts/list → [{name, ...}]         │
│  │                                              │
│  ├── Agent (POST /chat)                         │
│  │     ├── User message → LLM                   │
│  │     ├── LLM → tool call → execute → LLM      │
│  │     └── Final response                       │
│  │                                              │
│  └── stream_completion (GET /chat/stream)       │
│        └── LLM tokens → SSE events              │
└─────────────────────────────────────────────────┘
```

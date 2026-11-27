"""AI Agent with tool calling and conversation memory.

Provides :class:`Agent` — a high-level agent runner that:
1. Takes a user message
2. Decides whether to call a tool (via LLM function calling)
3. Executes the tool
4. Feeds the result back to the LLM
5. Returns the final response (or streams it token-by-token)

Supports any :class:`~rivex.ai.providers.Provider` (OpenAI, Anthropic).

Example::

    from rivex.ai import Agent, OpenAIProvider

    agent = Agent(
        name="research-assistant",
        system_prompt="You help users research topics.",
        provider=OpenAIProvider(model="gpt-4o"),
        tools=[search_db, calculate],
        max_iterations=5,
    )

    # Non-streaming
    response = await agent.run("What is the population of Tokyo?")

    # Streaming (token-by-token)
    async for token in agent.stream("Explain quantum computing"):
        yield token
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rivex.ai.providers import OpenAIProvider, Provider


class Agent:
    """LLM agent with tool calling and conversation memory.

    Args:
        name: Agent name (for logging / identification).
        system_prompt: System instructions for the LLM.
        provider: LLM provider (:class:`OpenAIProvider`,
            :class:`AnthropicProvider`). If a string is passed, creates
            an :class:`OpenAIProvider` with that model name.
        tools: List of callable functions the agent can invoke.
            Each function's docstring becomes the tool description;
            type hints become the parameter schema.
        max_iterations: Maximum tool-calling rounds before giving up
            (default 10). Prevents infinite loops.
        memory: Whether to maintain conversation history across
            :meth:`run` calls (default ``True``).
    """

    def __init__(
        self,
        name: str = "agent",
        *,
        system_prompt: str = "You are a helpful assistant.",
        provider: Provider | str = "gpt-4o",
        tools: list[Callable] | None = None,
        max_iterations: int = 10,
        memory: bool = True,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.provider = provider if isinstance(provider, Provider) else OpenAIProvider(model=provider)
        self.tools = tools or []
        self.max_iterations = max_iterations
        self._use_memory = memory
        self._memory: list[dict[str, str]] = []

    def clear_memory(self) -> None:
        """Clear conversation history."""
        self._memory.clear()

    def _build_tool_defs(self) -> list[dict]:
        """Build OpenAI-style tool definitions from registered functions."""
        import inspect

        defs = []
        for func in self.tools:
            sig = inspect.signature(func)
            properties = {}
            required = []
            for pname, param in sig.parameters.items():
                annotation = param.annotation
                json_type = "string"
                if annotation in (int, "int"):
                    json_type = "integer"
                elif annotation in (float, "float"):
                    json_type = "number"
                elif annotation in (bool, "bool"):
                    json_type = "boolean"
                properties[pname] = {"type": json_type}
                if param.default is inspect.Parameter.empty:
                    required.append(pname)

            defs.append({
                "name": func.__name__,
                "description": (func.__doc__ or "").strip(),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            })
        return defs

    def _execute_tool(self, name: str, arguments: dict) -> str:
        """Execute a tool by name with the given arguments."""
        for func in self.tools:
            if func.__name__ == name:
                result = func(**arguments)
                return str(result)
        return f"Error: tool '{name}' not found"

    async def run(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Run the agent on a user message (non-streaming).

        The agent may call tools multiple times before producing a final
        response. Each tool call round counts against ``max_iterations``.

        Args:
            message: User's input message.
            context: Optional context dict made available to tools
                via the ``_agent_context`` keyword argument.

        Returns:
            The agent's final text response.
        """
        messages = list(self._memory) if self._use_memory else []
        messages.append({"role": "user", "content": message})

        tool_defs = self._build_tool_defs() if self.tools else []

        for _ in range(self.max_iterations):
            if tool_defs:
                result = await self.provider.complete_with_tools(
                    messages, tool_defs, system=self.system_prompt
                )
                if result["tool_calls"]:
                    messages.append({"role": "assistant", "content": result["content"]})
                    for tc in result["tool_calls"]:
                        tool_result = self._execute_tool(tc["name"], tc["arguments"])
                        messages.append({"role": "tool", "content": tool_result, "name": tc["name"]})
                    continue
                final = result["content"]
            else:
                final = await self.provider.complete(messages, system=self.system_prompt)

            if self._use_memory:
                self._memory.append({"role": "user", "content": message})
                self._memory.append({"role": "assistant", "content": final})

            return final

        return "I've reached my maximum number of tool calls. Let me know if you'd like me to try a different approach."

    async def stream(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> Any:
        """Stream the agent's response token-by-token.

        If the agent calls tools, those execute silently first (non-streamed).
        Only the FINAL response is streamed.

        Args:
            message: User's input message.
            context: Optional context dict for tools.

        Yields:
            Text tokens (``str``) as they arrive from the LLM.
        """
        messages = list(self._memory) if self._use_memory else []
        messages.append({"role": "user", "content": message})

        tool_defs = self._build_tool_defs() if self.tools else []

        # If tools are registered, resolve tool calls first (non-streaming)
        if tool_defs:
            for _ in range(self.max_iterations):
                result = await self.provider.complete_with_tools(
                    messages, tool_defs, system=self.system_prompt
                )
                if result["tool_calls"]:
                    messages.append({"role": "assistant", "content": result["content"]})
                    for tc in result["tool_calls"]:
                        tool_result = self._execute_tool(tc["name"], tc["arguments"])
                        messages.append({"role": "tool", "content": tool_result, "name": tc["name"]})
                    continue
                # No more tool calls — stream the final response
                break

        # Stream the final response
        async for token in self.provider.stream(messages, system=self.system_prompt):
            yield token

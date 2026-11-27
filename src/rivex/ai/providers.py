"""LLM provider abstraction for OpenAI and Anthropic.

Provides a unified interface for calling different LLM providers,
so agents and streaming helpers can switch providers without code changes.

Requires:
    ``pip install openai`` for OpenAIProvider
    ``pip install anthropic`` for AnthropicProvider

Example::

    from rivex.ai.providers import OpenAIProvider

    provider = OpenAIProvider(model="gpt-4o", api_key="sk-...")
    response = await provider.complete([
        {"role": "user", "content": "Hello!"}
    ])
    # => "Hi there! How can I help?"

    async for token in provider.stream([
        {"role": "user", "content": "Write a haiku"}
    ]):
        print(token, end="", flush=True)
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any


class Provider(ABC):
    """Abstract LLM provider — implement :meth:`complete` and :meth:`stream`.

    Concrete implementations:
        - :class:`OpenAIProvider`
        - :class:`AnthropicProvider`
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g. ``"openai"``, ``"anthropic"``)."""
        ...

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> str:
        """Generate a completion (non-streaming).

        Args:
            messages: Chat messages (``[{"role": "user", "content": "..."}]``).
            system: Optional system prompt.
            temperature: Sampling temperature (0.0–2.0).
            max_tokens: Maximum tokens to generate.
            tools: Optional function-calling tool definitions.

        Returns:
            The assistant's text response.
        """
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Any:
        """Stream tokens from the LLM.

        Args:
            messages: Chat messages.
            system: Optional system prompt.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens.

        Yields:
            Text tokens (``str``) as they arrive.
        """
        ...

    async def complete_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict],
        *,
        system: str | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """Generate a completion that may call tools.

        Returns a dict with:
            - ``content``: text response (may be empty if tools called)
            - ``tool_calls``: list of ``{name, arguments}`` dicts
        """
        # Default: delegate to complete (tool calling not supported)
        text = await self.complete(messages, system=system, temperature=temperature, tools=tools)
        return {"content": text, "tool_calls": []}


class OpenAIProvider(Provider):
    """OpenAI GPT provider.

    Args:
        model: Model name (default ``"gpt-4o"``).
        api_key: API key (defaults to ``OPENAI_API_KEY`` env var).
        base_url: Optional custom base URL (for Azure, proxies, etc.).
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url

    @property
    def name(self) -> str:
        """Return the provider identifier used in logs and configs.

        Returns:
            The literal string ``"openai"``.
        """
        return "openai"

    def _get_client(self):
        """Lazily construct the underlying ``AsyncOpenAI`` client.

        Imports the ``openai`` package on demand so importing this module
        does not require the SDK to be installed.

        Returns:
            A configured ``AsyncOpenAI`` instance. The ``base_url`` is
            only set when the provider was constructed with one.

        Raises:
            ImportError: When the ``openai`` package is not installed.
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai package required: pip install openai") from None

        kwargs = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return AsyncOpenAI(**kwargs)

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> str:
        """Generate a non-streaming completion from the configured OpenAI model.

        Prepends an optional system message, forwards the rest of the
        conversation, and applies the supplied sampling and tool
        settings before awaiting a single ``chat.completions.create``
        response. ``tools`` are wrapped in the ``{type: function, function}``
        envelope the Chat Completions API expects.

        Args:
            messages: Chat messages in ``[{"role": ..., "content": ...}]``
                form. The ``role`` is one of ``"user"``, ``"assistant"``,
                or ``"tool"``.
            system: Optional system prompt to inject as the first message.
            temperature: Sampling temperature forwarded to the API.
            max_tokens: Optional cap on generated tokens.
            tools: Optional function-calling tool schemas to expose to
                the model.

        Returns:
            The assistant's text content. An empty string is returned
            when the model produced no text (e.g. it requested a tool
            call instead).
        """
        client = self._get_client()
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = [
                {"type": "function", "function": t} for t in tools
            ]

        response = await client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Any:
        """Stream chat completion tokens from the configured OpenAI model.

        Sends the same payload as :meth:`complete` but with ``stream=True``
        and yields each non-empty ``delta.content`` token as it arrives.
        Empty deltas (for example role-only frames) are skipped.

        Args:
            messages: Chat messages in ``[{"role": ..., "content": ...}]`` form.
            system: Optional system prompt injected as the first message.
            temperature: Sampling temperature forwarded to the API.
            max_tokens: Optional cap on generated tokens.

        Yields:
            Individual text tokens (``str``) as they are produced by the
            model.
        """
        client = self._get_client()
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        response = await client.chat.completions.create(**kwargs)
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def complete_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict],
        *,
        system: str | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """Run a chat completion and surface any requested tool calls.

        Each tool schema is wrapped in the ``{type: function, function}``
        envelope expected by the Chat Completions API. When the model
        returns one or more ``tool_calls`` entries, their ``arguments``
        are JSON-decoded into Python objects before being placed on
        the returned dict.

        Args:
            messages: Chat messages in ``[{"role": ..., "content": ...}]`` form.
            tools: Function-calling tool schemas to expose to the model.
            system: Optional system prompt injected as the first message.
            temperature: Sampling temperature forwarded to the API.

        Returns:
            A dict with ``content`` (the assistant's text, possibly
            empty) and ``tool_calls`` (a list of ``{"name", "arguments"}``
            dicts; empty when the model did not call any tool).
        """
        client = self._get_client()
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        response = await client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            temperature=temperature,
            tools=[{"type": "function", "function": t} for t in tools],
        )
        msg = response.choices[0].message
        tool_calls = []
        if msg.tool_calls:
            import json

            for tc in msg.tool_calls:
                tool_calls.append({
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                })
        return {"content": msg.content or "", "tool_calls": tool_calls}


class AnthropicProvider(Provider):
    """Anthropic Claude provider.

    Args:
        model: Model name (default ``"claude-sonnet-4-20250514"``).
        api_key: API key (defaults to ``ANTHROPIC_API_KEY`` env var).
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        *,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    @property
    def name(self) -> str:
        """Return the provider identifier used in logs and configs.

        Returns:
            The literal string ``"anthropic"``.
        """
        return "anthropic"

    def _get_client(self):
        """Lazily construct the underlying ``AsyncAnthropic`` client.

        Imports the ``anthropic`` package on demand so importing this
        module does not require the SDK to be installed.

        Returns:
            A configured ``AsyncAnthropic`` instance bound to the
            provider's API key.

        Raises:
            ImportError: When the ``anthropic`` package is not installed.
        """
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise ImportError("anthropic package required: pip install anthropic") from None
        return AsyncAnthropic(api_key=self.api_key)

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> str:
        """Generate a non-streaming completion from the configured Anthropic model.

        Forwards the request to ``messages.create`` with the supplied
        conversation, optional system prompt, sampling temperature, and
        a token budget that defaults to ``4096`` when the caller omits
        one. The first ``text`` block on the response is returned; an
        empty string is returned when the response carries no content
        blocks.

        Args:
            messages: Chat messages in ``[{"role": ..., "content": ...}]``
                form expected by the Anthropic API.
            system: Optional system prompt passed through the API's
                top-level ``system`` parameter.
            temperature: Sampling temperature forwarded to the API.
            max_tokens: Maximum tokens to generate; defaults to ``4096``
                when not provided.
            tools: Optional tool schemas. Accepted for API parity with
                the abstract base class; Anthropic's tool-use API is not
                invoked here.

        Returns:
            The assistant's text content, or an empty string when the
            response carried no text blocks.
        """
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }
        if system:
            kwargs["system"] = system

        response = await client.messages.create(**kwargs)
        return response.content[0].text if response.content else ""

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Any:
        """Stream text tokens from the configured Anthropic model.

        Opens an Anthropic message stream with the same defaults as
        :meth:`complete` and yields each text delta produced by the
        SDK's ``text_stream`` iterator.

        Args:
            messages: Chat messages in ``[{"role": ..., "content": ...}]`` form.
            system: Optional system prompt passed through the API's
                top-level ``system`` parameter.
            temperature: Sampling temperature forwarded to the API.
            max_tokens: Maximum tokens to generate; defaults to ``4096``
                when not provided.

        Yields:
            Text deltas (``str``) as they arrive from the streaming
            response.
        """
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }
        if system:
            kwargs["system"] = system

        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

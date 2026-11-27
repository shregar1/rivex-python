"""SSE streaming helper for LLM chat completions.

Wraps any :class:`~rivex.ai.providers.Provider` into a Rivex-compatible
SSE response. One function — mount on any route.

Example::

    from rivex import Rivex
    from rivex.ai import stream_completion, OpenAIProvider

    app = Rivex()
    provider = OpenAIProvider(model="gpt-4o")

    @app.post("/chat")
    async def chat(body: dict):
        return stream_completion(
            provider,
            messages=body["messages"],
            system="You are a helpful assistant.",
        )

The returned response automatically:
- Sets ``Content-Type: text/event-stream``
- Streams tokens as SSE ``data:`` events
- Sends ``[DONE]`` on completion
- Handles errors gracefully (sends error event, closes stream)
"""

from __future__ import annotations

import json

from rivex.ai.providers import Provider


def stream_completion(
    provider: Provider,
    messages: list[dict[str, str]],
    *,
    system: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> dict:
    """Create a streaming SSE response from an LLM provider.

    Returns a dict that  response pipeline recognises as a
    streaming response. The handler should ``return`` this directly.

    Args:
        provider: An LLM provider (:class:`OpenAIProvider`,
            :class:`AnthropicProvider`).
        messages: Chat messages.
        system: Optional system prompt.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens to generate.

    Returns:
        A response dict with ``stream=True`` that Rivex streams via SSE.

    Note:
        This uses  built-in streaming response mechanism.
        The client receives ``data: {token}\\n\\n`` events followed
        by ``data: [DONE]\\n\\n``.
    """
    # We need to return something Rivex can stream.
    #  EventSourceResponse expects a content producer.
    # For now, we build a raw response with SSE headers and
    # a streaming body.
    #
    # The streaming is handled by returning a special dict that
    # the framework recognises. We use the stream_id mechanism.

    # Import here to avoid circular imports at module load
    try:
        from rivex_core import create_stream_sender
        stream_id, sender = create_stream_sender(buffer_size=16)
    except ImportError:
            raise ImportError("rivex_core extension required for streaming") from None

    import asyncio

    async def _produce():
        """Background task that streams LLM tokens into the SSE channel."""
        try:
            async for token in provider.stream(
                messages,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                sse_data = f"data: {json.dumps({'content': token})}\n\n"
                sender.send_chunk(sse_data.encode("utf-8"))
            sender.send_chunk(b"data: [DONE]\n\n")
        except Exception as exc:
            error_data = json.dumps({"error": str(exc)})
            sender.send_chunk(f"data: {error_data}\n\n".encode())
        finally:
            sender.close()

    # Schedule the producer
    asyncio.ensure_future(_produce())

    return {
        "status": 200,
        "headers": [
            ("content-type", "text/event-stream"),
            ("cache-control", "no-cache"),
            ("connection", "keep-alive"),
            ("x-stream-id", str(stream_id)),
        ],
        "stream_id": stream_id,
        "body": b"",
    }

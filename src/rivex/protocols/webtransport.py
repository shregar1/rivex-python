from __future__ import annotations

import asyncio
import logging
import os
import ssl
import threading
import uuid
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("rivex.webtransport")


class WebTransportServer:
    """WebTransport server over HTTP/3 (QUIC) using aioquic.

    WebTransport enables low-latency bidirectional communication
    over QUIC (UDP), supporting both unidirectional and bidirectional
    streams as well as datagrams — ideal for gaming, real-time media,
    and live collaboration.

    Usage::

        server = WebTransportServer(
            host="0.0.0.0", port=4433,
            cert_path="cert.pem", key_path="key.pem",
        )

        @server.on_connect
        async def on_connect(session):
            print(f"Session {session.id} connected")

        @server.on_datagram
        async def on_datagram(session, data):
            await session.send_datagram(b"echo: " + data)

        server.start()
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 4433,
        cert_path: str = "",
        key_path: str = "",
    ):
        self._host = host
        self._port = port
        self._cert_path = cert_path or os.environ.get("WEBTRANSPORT_CERT", "cert.pem")
        self._key_path = key_path or os.environ.get("WEBTRANSPORT_KEY", "key.pem")
        self._server = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._sessions: dict[str, WebTransportSession] = {}
        self._on_connect: Callable | None = None
        self._on_disconnect: Callable | None = None
        self._on_datagram: Callable | None = None
        self._on_stream: Callable | None = None

    @property
    def on_connect(self) -> Callable | None:
        """Return the connect handler currently bound to the server, if any.

        Returns:
            The async callable set via the ``on_connect`` setter, or
            ``None`` if no handler has been registered.
        """
        return self._on_connect

    @on_connect.setter
    def on_connect(self, func: Callable) -> None:
        """Register the async connect handler invoked for every new session.

        Args:
            func: Async callable accepting the freshly constructed
                :class:`WebTransportSession` as its sole argument.
        """
        self._on_connect = func

    @property
    def on_disconnect(self) -> Callable | None:
        """Return the disconnect handler currently bound to the server, if any.

        Returns:
            The async callable set via the ``on_disconnect`` setter, or
            ``None`` if no handler has been registered.
        """
        return self._on_disconnect

    @on_disconnect.setter
    def on_disconnect(self, func: Callable) -> None:
        """Register the async disconnect handler invoked when a session ends.

        Args:
            func: Async callable accepting the closing
                :class:`WebTransportSession` as its sole argument.
        """
        self._on_disconnect = func

    @property
    def on_datagram(self) -> Callable | None:
        """Return the datagram handler currently bound to the server, if any.

        Returns:
            The async callable set via the ``on_datagram`` setter, or
            ``None`` if no handler has been registered.
        """
        return self._on_datagram

    @on_datagram.setter
    def on_datagram(self, func: Callable) -> None:
        """Register the datagram handler invoked for every incoming datagram.

        Args:
            func: Async callable receiving ``(session, data)`` where
                ``data`` is the raw datagram payload.
        """
        self._on_datagram = func

    @property
    def on_stream(self) -> Callable | None:
        """Return the stream handler currently bound to the server, if any.

        Returns:
            The async callable set via the ``on_stream`` setter, or
            ``None`` if no handler has been registered.
        """
        return self._on_stream

    @on_stream.setter
    def on_stream(self, func: Callable) -> None:
        """Register the stream handler invoked for every incoming stream.

        Args:
            func: Async callable receiving ``(session, data)`` for each
                chunk read from a stream.
        """
        self._on_stream = func

    async def _handle_session(self, session_id: str, reader, writer) -> None:
        """Drive a single WebTransport session through its lifecycle.

        Constructs a :class:`WebTransportSession`, fires the connect
        handler, then loops reading up to 64 KiB at a time and
        dispatching to the datagram handler. Any exception is swallowed
        so the surrounding server loop keeps accepting new sessions;
        the disconnect handler is always invoked on the way out.

        Args:
            session_id: UUID for the new session.
            reader: Async stream reader for the underlying QUIC stream.
            writer: Async stream writer used to send responses.
        """
        session = WebTransportSession(session_id, reader, writer)
        self._sessions[session_id] = session

        if self._on_connect:
            await self._on_connect(session)

        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                if self._on_datagram:
                    await self._on_datagram(session, data)
        except Exception:
            pass
        finally:
            self._sessions.pop(session_id, None)
            if self._on_disconnect:
                await self._on_disconnect(session)

    async def _run_server(self) -> None:
        """Run the ``aioquic`` WebTransport server until cancellation.

        Builds a ``QuicConfiguration`` with the ``h3`` and
        ``webtransport`` ALPN identifiers, loads the configured TLS
        chain, and starts a serving loop on ``host:port``. Missing
        certificate files are warned about but do not stop startup.
        Errors during the serve loop are logged and the coroutine
        returns.
        """
        try:
            from aioquic.asyncio import serve
            from aioquic.quic.configuration import QuicConfiguration
        except ImportError:
            logger.error(
                "aioquic library required for WebTransport. "
                "Install with: pip install aioquic"
            )
            return

        configuration = QuicConfiguration(
            alpn_protocols=["h3", "webtransport"],
            is_client=False,
            max_data=10485760,
            max_stream_data=1048576,
        )

        if not os.path.exists(self._cert_path) or not os.path.exists(self._key_path):
            logger.warning(
                f"TLS certificate required. Generate with: "
                f"openssl req -x509 -newkey rsa:2048 "
                f"-keyout {self._key_path} -out {self._cert_path} -days 365 -nodes"
            )

        configuration.load_cert_chain(self._cert_path, self._key_path)

        async def session_handler(reader, writer):
            """Bridge a raw QUIC stream pair into a :meth:`_handle_session` call.

            Allocates a fresh UUID and dispatches the (reader, writer)
            pair into the server's session lifecycle handler. Used as
            the ``create_protocol`` callback for ``aioquic.serve``.

            Args:
                reader: Async stream reader for the new connection.
                writer: Async stream writer used to send the response.
            """
            session_id = str(uuid.uuid4())
            await self._handle_session(session_id, reader, writer)

        try:
            self._server = await serve(
                host=self._host,
                port=self._port,
                configuration=configuration,
                create_protocol=session_handler,
            )
            self._running = True
            logger.info(
                f"WebTransport server listening on UDP {self._host}:{self._port}"
            )
            await self._server.wait_closed()
        except Exception as e:
            logger.error(f"WebTransport server error: {e}")

    def start(self) -> None:
        """Launch the WebTransport server on a dedicated daemon thread.

        Spawns a background thread that owns a fresh event loop and
        runs :meth:`_run_server` to completion. Already-running
        servers are left untouched.
        """
        if self._running:
            return

        def target():
            """Thread entry point: drive :meth:`_run_server` on a private loop.

            Each server instance gets its own loop so multiple
            WebTransport listeners can coexist without sharing
            asyncio primitives.
            """
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_server())

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the WebTransport server.

        Clears the running flag, asks the underlying ``aioquic`` server
        to close, and logs the shutdown. Safe to call when the server
        was never started.
        """
        self._running = False
        if self._server:
            self._server.close()
        logger.info("WebTransport server stopped")

    @property
    def sessions(self) -> dict[str, WebTransportSession]:
        """Return a snapshot mapping session id to live :class:`WebTransportSession`.

        Returns:
            A new ``dict`` so callers can safely iterate without
            worrying about concurrent mutation. Closed sessions are
            removed by :meth:`_handle_session` before they would
            appear here.
        """
        return dict(self._sessions)

    def broadcast_datagram(self, data: bytes) -> None:
        """Send ``data`` to every currently connected session.

        Exceptions raised by individual sessions are swallowed so a
        single broken peer cannot interrupt the broadcast.

        Args:
            data: Raw datagram payload to deliver to each session.
        """
        for session in self._sessions.values():
            try:
                session._queue_datagram(data)
            except Exception:
                pass


class WebTransportSession:
    """Represents a single WebTransport client session."""

    def __init__(self, session_id: str, reader, writer):
        self.id = session_id
        self._reader = reader
        self._writer = writer
        self._connected = True
        self._metadata: dict[str, Any] = {}

    async def send_datagram(self, data: bytes) -> None:
        """Write a single datagram to the underlying QUIC stream.

        Args:
            data: Raw payload bytes to send.

        Raises:
            ConnectionError: When the session has already been closed
                via :meth:`close`.
        """
        if not self._connected:
            raise ConnectionError("Session is closed")
        self._writer.write(data)
        await self._writer.drain()

    async def send_stream(self, stream_id: int, data: bytes) -> None:
        """Send a chunk of stream data.

        Thin convenience wrapper that delegates to
        :meth:`send_datagram` because the current implementation treats
        streams and datagrams identically. ``stream_id`` is accepted
        for API compatibility with the WebTransport spec.

        Args:
            stream_id: Identifier of the stream to write to. Currently
                unused beyond the signature.
            data: Raw payload bytes to send.
        """
        await self.send_datagram(data)

    async def receive_datagram(self) -> bytes:
        """Read up to 64 KiB from the underlying stream.

        Returns:
            The raw bytes that were available. An empty ``bytes``
            value indicates the peer has closed the connection.
        """
        data = await self._reader.read(65536)
        return data

    async def close(self) -> None:
        """Mark the session as disconnected and close the underlying writer.

        Safe to call more than once — the writer is closed once and
        any exception during the close handshake is swallowed so the
        caller never has to wrap it in a try/except.
        """
        self._connected = False
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:
            pass

    @property
    def connected(self) -> bool:
        """Return whether this session is still considered open.

        Returns:
            ``True`` until :meth:`close` is called (or the server's
            session handler decides to drop the session).
        """
        return self._connected

    def __getitem__(self, key: str) -> Any:
        return self._metadata[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._metadata[key] = value


class WebTransportClient:
    """WebTransport client for connecting to remote WebTransport servers."""

    def __init__(self):
        self._session = None

    async def connect(
        self, url: str, cert_path: str | None = None
    ) -> WebTransportSession:
        """Open a WebTransport session to ``url`` and return the handle.

        Builds a ``QuicConfiguration`` with the ``h3`` and
        ``webtransport`` ALPN identifiers, configures TLS verification
        from ``cert_path`` (or disables it when omitted), opens an
        ``aioquic`` client connection, and wraps the resulting
        reader/writer in a :class:`WebTransportSession`.

        Args:
            url: The full ``https://host:port`` URL to connect to.
            cert_path: Optional path to a CA bundle for verifying the
                server certificate. When ``None``, certificate
                verification is disabled (``CERT_NONE``).

        Returns:
            A live :class:`WebTransportSession` bound to the remote
            endpoint.

        Raises:
            ImportError: When the optional ``aioquic`` dependency is
                not installed.
        """
        try:
            from aioquic.asyncio.client import connect
            from aioquic.quic.configuration import QuicConfiguration
        except ImportError:
            raise ImportError("aioquic library required")

        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 4433

        configuration = QuicConfiguration(alpn_protocols=["h3", "webtransport"], is_client=True)
        if cert_path:
            configuration.load_verify_locations(cert_path)
        else:
            configuration.verify_mode = ssl.CERT_NONE

        async with connect(host, port, configuration=configuration) as client:
            session_id = str(uuid.uuid4())
            self._session = WebTransportSession(session_id, client, client)
            return self._session

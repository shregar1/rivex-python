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
        return self._on_connect

    @on_connect.setter
    def on_connect(self, func: Callable) -> None:
        self._on_connect = func

    @property
    def on_disconnect(self) -> Callable | None:
        return self._on_disconnect

    @on_disconnect.setter
    def on_disconnect(self, func: Callable) -> None:
        self._on_disconnect = func

    @property
    def on_datagram(self) -> Callable | None:
        return self._on_datagram

    @on_datagram.setter
    def on_datagram(self, func: Callable) -> None:
        self._on_datagram = func

    @property
    def on_stream(self) -> Callable | None:
        return self._on_stream

    @on_stream.setter
    def on_stream(self, func: Callable) -> None:
        self._on_stream = func

    async def _handle_session(self, session_id: str, reader, writer) -> None:
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
        if self._running:
            return

        def target():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_server())

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._server:
            self._server.close()
            logger.info("WebTransport server stopped")

    @property
    def sessions(self) -> dict[str, WebTransportSession]:
        return dict(self._sessions)

    def broadcast_datagram(self, data: bytes) -> None:
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
        if not self._connected:
            raise ConnectionError("Session is closed")
        self._writer.write(data)
        await self._writer.drain()

    async def send_stream(self, stream_id: int, data: bytes) -> None:
        await self.send_datagram(data)

    async def receive_datagram(self) -> bytes:
        data = await self._reader.read(65536)
        return data

    async def close(self) -> None:
        self._connected = False
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:
            pass

    @property
    def connected(self) -> bool:
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

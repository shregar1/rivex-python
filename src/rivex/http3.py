from __future__ import annotations

import asyncio
import logging
import os
import ssl
import threading
from typing import Any

logger = logging.getLogger("rivex.http3")


class Http3Server:
    """HTTP/3 (QUIC) server using ``aioquic``.

    Runs on a separate UDP port alongside the existing HTTP server.

    Usage::

        server = Http3Server(host="0.0.0.0", port=4433,
                             cert_path="cert.pem", key_path="key.pem")
        server.start()

    Or via app convenience method::

        app.enable_http3(port=4433, cert_path="cert.pem", key_path="key.pem")
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 4433,
        cert_path: str = "",
        key_path: str = "",
        handler: Any = None,
    ):
        self._host = host
        self._port = port
        self._cert_path = cert_path or os.environ.get("HTTP3_CERT", "cert.pem")
        self._key_path = key_path or os.environ.get("HTTP3_KEY", "key.pem")
        self._handler = handler
        self._server = None
        self._thread: threading.Thread | None = None
        self._running = False

    def _create_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(self._cert_path, self._key_path)
        ctx.set_alpn_protocols(["h3"])
        return ctx

    async def _handle_quic(self) -> None:
        try:
            from aioquic.asyncio import serve
            from aioquic.quic.configuration import QuicConfiguration
            from aioquic.asyncio.protocol import QuicConnectionProtocol
        except ImportError:
            logger.error("aioquic library required. Install with: pip install aioquic")
            return

        configuration = QuicConfiguration(
            alpn_protocols=["h3"],
            is_client=False,
            max_data=1048576,
            max_stream_data=262144,
        )
        configuration.load_cert_chain(self._cert_path, self._key_path)

        async def handler_func(reader, writer):
            data = await reader.read(65536)
            if self._handler:
                response = await self._handler(data)
                writer.write(response)
            await writer.drain()
            writer.close()

        try:
            self._server = await serve(
                host=self._host,
                port=self._port,
                configuration=configuration,
                create_protocol=handler_func,
            )
            self._running = True
            logger.info(f"HTTP/3 server listening on UDP {self._host}:{self._port}")
            await self._server.wait_closed()
        except Exception as e:
            logger.error(f"HTTP/3 server error: {e}")

    def start(self) -> None:
        if self._running:
            return
        if not os.path.exists(self._cert_path) or not os.path.exists(self._key_path):
            logger.warning(
                f"TLS certificate required for HTTP/3. "
                f"Generate with: openssl req -x509 -newkey rsa:2048 "
                f"-keyout {self._key_path} -out {self._cert_path} -days 365 -nodes"
            )

        def target():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._handle_quic())

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._server:
            self._server.close()
            logger.info("HTTP/3 server stopped")


class Http3Client:
    """HTTP/3 (QUIC) client for making requests from handlers.

    Usage::

        client = Http3Client()
        response = await client.get("https://example.com")
    """

    def __init__(self):
        self._client = None

    async def get(self, url: str) -> dict:
        try:
            from aioquic.asyncio.client import connect
            from aioquic.quic.configuration import QuicConfiguration
        except ImportError:
            return {"error": "aioquic library required"}

        configuration = QuicConfiguration(alpn_protocols=["h3"], is_client=True)
        configuration.verify_mode = ssl.CERT_NONE

        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 443

        try:
            async with connect(host, port, configuration=configuration) as client:
                response = await client.get(url)
                return {"status": response.status_code, "body": response.data.decode()}
        except Exception as e:
            return {"error": str(e)}

    async def post(self, url: str, data: bytes = b"") -> dict:
        try:
            from aioquic.asyncio.client import connect
        except ImportError:
            return {"error": "aioquic library required"}

        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 443

        configuration = QuicConfiguration(alpn_protocols=["h3"], is_client=True)
        configuration.verify_mode = ssl.CERT_NONE

        try:
            async with connect(host, port, configuration=configuration) as client:
                response = await client.post(url, data=data)
                return {"status": response.status_code, "body": response.data.decode()}
        except Exception as e:
            return {"error": str(e)}

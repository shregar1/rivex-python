from __future__ import annotations

import asyncio
import logging
import os
import ssl
import threading
from typing import Any

logger = logging.getLogger("rivex.quic")


class QUICServer:
    """HTTP/3 (QUIC) server using ``aioquic``.

    Runs on a separate UDP port alongside the existing HTTP server.

    Usage::

        server = QUICServer(host="0.0.0.0", port=4433,
                             cert_path="cert.pem", key_path="key.pem")
        server.start()

    Or via app convenience method::

        app.enable_quic(port=4433, cert_path="cert.pem", key_path="key.pem")
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
        """Build an ``ssl.SSLContext`` for terminating HTTP/3 connections.

        Loads the certificate chain from ``self._cert_path`` /
        ``self._key_path`` and constrains ALPN to ``"h3"``.

        Returns:
            A configured ``ssl.SSLContext`` ready to hand to ``aioquic``.
        """
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(self._cert_path, self._key_path)
        ctx.set_alpn_protocols(["h3"])
        return ctx

    async def _handle_quic(self) -> None:
        """Run the QUIC server until cancelled.

        Imports ``aioquic``, configures ALPN and stream limits, opens a
        connection per incoming request, awaits ``wait_closed`` and
        returns silently if the optional ``aioquic`` dependency is
        missing.
        """
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
            """Drive a single incoming QUIC stream to completion.

            Reads up to 64 KiB, optionally forwards it to the bound
            ``self._handler``, writes the response back and closes the
            stream.

            Args:
                reader: The async stream reader for the new connection.
                writer: The async stream writer used to send the response.
            """
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
        """Launch the HTTP/3 server on a dedicated daemon thread.

        Warns when the certificate or key file is missing, then
        installs a fresh asyncio event loop on the background thread
        and runs :meth:`_handle_quic` until it returns. Already-running
        servers are left untouched.
        """
        if self._running:
            return
        if not os.path.exists(self._cert_path) or not os.path.exists(self._key_path):
            logger.warning(
                f"TLS certificate required for HTTP/3. "
                f"Generate with: openssl req -x509 -newkey rsa:2048 "
                f"-keyout {self._key_path} -out {self._cert_path} -days 365 -nodes"
            )

        def target():
            """Thread entry point: drive :meth:`_handle_quic` to completion on a private loop.

            Each server instance gets its own loop so multiple HTTP/3
            listeners can coexist without sharing asyncio primitives.
            """
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._handle_quic())

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the HTTP/3 server.

        Clears the running flag, asks the underlying ``aioquic`` server
        to close, and logs the shutdown. Safe to call when the server
        was never started.
        """
        self._running = False
        if self._server:
            self._server.close()
        logger.info("HTTP/3 server stopped")


class QUICClient:
    """HTTP/3 (QUIC) client for making requests from handlers.

    Usage::

        client = QUICClient()
        response = await client.get("https://example.com")
    """

    def __init__(self):
        self._client = None

    async def get(self, url: str) -> dict:
        """Issue a single HTTP/3 ``GET`` to ``url`` and return the parsed response.

        Imports ``aioquic`` lazily; when the optional dependency is
        missing the call resolves to ``{"error": "aioquic library
        required"}`` instead of raising. Network failures are caught
        and returned as ``{"error": str(exc)}`` so the caller does not
        need a ``try``/``except``.

        Args:
            url: Absolute ``https://`` URL to fetch.

        Returns:
            A ``{"status": int, "body": str}`` dict on success, or
            ``{"error": str}`` when the library is missing or the
            request failed.
        """
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
        """Issue a single HTTP/3 ``POST`` to ``url`` and return the parsed response.

        Same error-handling contract as :meth:`get` — missing library
        and network errors are returned as ``{"error": str}`` rather
        than propagated, so a handler can simply check the key.

        Args:
            url: Absolute ``https://`` URL to POST to.
            data: Raw request body bytes. Defaults to empty.

        Returns:
            A ``{"status": int, "body": str}`` dict on success, or
            ``{"error": str}`` when the library is missing or the
            request failed.
        """
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

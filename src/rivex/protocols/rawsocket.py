from __future__ import annotations

import asyncio
import logging
import os
import socket
import ssl
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("rivex.rawsocket")


class RawTCPServer:
    """Raw TCP server for custom protocol handling.

    Accepts raw TCP connections and dispatches them to a handler
    function, allowing implementation of any TCP-based protocol.

    Usage::

        server = RawTCPServer(host="0.0.0.0", port=9000)

        @server.on_connect
        async def handle_client(reader, writer):
            data = await reader.read(1024)
            writer.write(b"echo: " + data)
            await writer.drain()
            writer.close()

        server.start()
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9000,
        ssl_cert: str | None = None,
        ssl_key: str | None = None,
        max_buffer_size: int = 65536,
    ):
        self._host = host
        self._port = port
        self._ssl_cert = ssl_cert
        self._ssl_key = ssl_key
        self._max_buffer_size = max_buffer_size
        self._server = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._handler: Callable | None = None
        self._on_connect: Callable | None = None
        self._on_disconnect: Callable | None = None

    @property
    def on_connect(self) -> Callable | None:
        return self._on_connect

    @on_connect.setter
    def on_connect(self, func: Callable) -> None:
        self._on_connect = func
        self._handler = func

    @property
    def on_disconnect(self) -> Callable | None:
        return self._on_disconnect

    @on_disconnect.setter
    def on_disconnect(self, func: Callable) -> None:
        self._on_disconnect = func

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        try:
            if self._on_connect:
                await self._on_connect(reader, writer)
        except Exception as e:
            logger.error(f"TCP handler error for {peer}: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            if self._on_disconnect:
                await self._on_disconnect(peer)

    async def _run_server(self) -> None:
        ssl_context = None
        if self._ssl_cert and self._ssl_key:
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(self._ssl_cert, self._ssl_key)

        try:
            self._server = await asyncio.start_server(
                self._handle_client,
                host=self._host,
                port=self._port,
                ssl=ssl_context,
                limit=self._max_buffer_size,
            )
            self._running = True
            logger.info(f"Raw TCP server listening on {self._host}:{self._port}")
            async with self._server:
                await self._server.serve_forever()
        except Exception as e:
            logger.error(f"TCP server error: {e}")

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
            logger.info("Raw TCP server stopped")


class UnixSocketServer:
    """Unix domain socket server for local IPC.

    Usage::

        server = UnixSocketServer(path="/tmp/rivex.sock")

        @server.on_connect
        async def handle_client(reader, writer):
            data = await reader.read(1024)
            writer.write(b"pong")
            await writer.drain()

        server.start()
    """

    def __init__(self, path: str = "/tmp/rivex.sock", max_buffer_size: int = 65536):
        self._path = path
        self._max_buffer_size = max_buffer_size
        self._server = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._handler: Callable | None = None

    @property
    def on_connect(self) -> Callable | None:
        return self._handler

    @on_connect.setter
    def on_connect(self, func: Callable) -> None:
        self._handler = func

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            if self._handler:
                await self._handler(reader, writer)
        except Exception as e:
            logger.error(f"Unix socket handler error: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _run_server(self) -> None:
        if os.path.exists(self._path):
            os.unlink(self._path)

        try:
            self._server = await asyncio.start_unix_server(
                self._handle_client,
                path=self._path,
                limit=self._max_buffer_size,
            )
            os.chmod(self._path, 0o777)
            self._running = True
            logger.info(f"Unix socket server listening on {self._path}")
            async with self._server:
                await self._server.serve_forever()
        except Exception as e:
            logger.error(f"Unix socket server error: {e}")

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
            logger.info("Unix socket server stopped")


class UDPBroadcastServer:
    """UDP broadcast/datagram server for custom protocols.

    Usage::

        server = UDPBroadcastServer(host="0.0.0.0", port=9999)

        @server.on_message
        async def handle_message(data, addr):
            print(f"Received from {addr}: {data}")
            await server.send(b"ack", addr)

        server.start()
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 9999):
        self._host = host
        self._port = port
        self._transport = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._on_message: Callable | None = None
        self._protocol = None

    @property
    def on_message(self) -> Callable | None:
        return self._on_message

    @on_message.setter
    def on_message(self, func: Callable) -> None:
        self._on_message = func

    class _UDPProtocol(asyncio.DatagramProtocol):
        def __init__(self, server: UDPBroadcastServer):
            self._server = server

        def datagram_received(self, data: bytes, addr: tuple) -> None:
            if self._server._on_message:
                try:
                    loop = asyncio.get_event_loop()
                    asyncio.ensure_future(self._server._on_message(data, addr))
                except Exception:
                    pass

        def error_received(self, exc: Exception) -> None:
            logger.error(f"UDP error: {exc}")

    async def send(self, data: bytes, addr: tuple[str, int]) -> None:
        if self._transport:
            self._transport.sendto(data, addr)

    async def _run_server(self) -> None:
        loop = asyncio.get_running_loop()
        self._protocol = self._UDPProtocol(self)
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: self._protocol,
            local_addr=(self._host, self._port),
        )
        self._running = True
        logger.info(f"UDP server listening on {self._host}:{self._port}")

    def start(self) -> None:
        if self._running:
            return

        def target():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_server())
            loop.run_forever()

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._transport:
            self._transport.close()
            logger.info("UDP server stopped")

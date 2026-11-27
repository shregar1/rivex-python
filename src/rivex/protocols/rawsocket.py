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
        """Return the currently registered connect handler, if any."""
        return self._on_connect

    @on_connect.setter
    def on_connect(self, func: Callable) -> None:
        """Register the connect handler and alias it as the main handler.

        Args:
            func: Async callable invoked once per accepted client.
        """
        self._on_connect = func
        self._handler = func

    @property
    def on_disconnect(self) -> Callable | None:
        """Return the currently registered disconnect handler, if any."""
        return self._on_disconnect

    @on_disconnect.setter
    def on_disconnect(self, func: Callable) -> None:
        """Register the disconnect handler.

        Args:
            func: Async callable invoked with the peer ``address`` tuple
                after the writer has been closed.
        """
        self._on_disconnect = func

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Drive a single accepted TCP client through its lifecycle.

        Invokes ``self._on_connect`` with the stream pair, then
        unconditionally closes the writer and finally invokes
        ``self._on_disconnect`` with the peer address. Handler errors
        are logged but never re-raised so the surrounding server loop
        keeps accepting new clients.
        """
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
        """Run the TCP server until cancelled.

        Builds an SSL context from ``ssl_cert`` / ``ssl_key`` when both
        are configured, opens ``asyncio.start_server`` on the bound
        ``host`` / ``port``, then enters ``serve_forever`` until the
        server is closed. Errors during startup are logged and the
        coroutine returns.
        """
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
        """Launch the TCP server on a dedicated daemon thread.

        The thread installs a fresh asyncio event loop, runs
        ``_run_server`` to completion and blocks in ``run_forever`` so
        the server keeps accepting clients. Already-running servers
        are left as-is.
        """
        if self._running:
            return

        def target():
            """Thread entry point: build a loop and execute ``_run_server``.

            Each server instance gets its own loop so that multiple
            servers can coexist without sharing asyncio primitives.
            """
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_server())

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the TCP server.

        Closes the underlying ``asyncio.Server`` so the
        ``serve_forever`` awaitable in ``_run_server`` returns. The
        ``_running`` flag is reset and the closure of an individual
        client writer happens inside ``_handle_client``.
        """
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
        """Return the currently registered Unix-socket handler."""
        return self._handler

    @on_connect.setter
    def on_connect(self, func: Callable) -> None:
        """Register the handler invoked for each accepted Unix-socket client.

        Args:
            func: Async callable accepting ``(reader, writer)``.
        """
        self._handler = func

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Drive a single accepted Unix-socket client through its lifecycle.

        Invokes ``self._handler`` (if set) and then closes the writer.
        Handler exceptions are logged and swallowed so the server keeps
        accepting further connections.
        """
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
        """Run the Unix-socket server until cancelled.

        Removes any pre-existing socket file at ``self._path``, opens
        ``asyncio.start_unix_server``, loosens them to mode ``0o777``
        so any local process may connect, and finally enters
        ``serve_forever``. Startup errors are logged and the coroutine
        returns cleanly.
        """
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
        """Launch the Unix-socket server on a dedicated daemon thread.

        The thread installs a fresh asyncio event loop and runs
        ``_run_server`` to completion. Already-running servers are
        left as-is.
        """
        if self._running:
            return

        def target():
            """Thread entry point: build a loop and execute ``_run_server``.

            Each Unix-socket server gets its own loop so that multiple
            servers can coexist without sharing asyncio primitives.
            """
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_server())

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the Unix-socket server.

        Closes the underlying ``asyncio.Server`` so the
        ``serve_forever`` awaitable in ``_run_server`` returns. The
        ``_running`` flag is reset and per-client writer cleanup
        happens inside ``_handle_client``.
        """
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
        """Return the currently registered datagram handler, if any."""
        return self._on_message

    @on_message.setter
    def on_message(self, func: Callable) -> None:
        """Register the datagram handler invoked for every incoming UDP packet.

        Args:
            func: Async callable accepting ``(data, addr)``.
        """
        self._on_message = func

    class _UDPProtocol(asyncio.DatagramProtocol):
        def __init__(self, server: UDPBroadcastServer):
            """Store the owning server so callbacks can reach the handler.

            Args:
                server: The :class:`UDPBroadcastServer` that owns this
                    protocol instance.
            """
            self._server = server

        def datagram_received(self, data: bytes, addr: tuple) -> None:
            """Forward an incoming datagram to the server's handler.

            Schedules ``self._server._on_message(data, addr)`` on the
            running event loop. Errors raised while scheduling are
            swallowed so the transport stays open.

            Args:
                data: The raw datagram payload.
                addr: ``(host, port)`` tuple of the sender.
            """
            if self._server._on_message:
                try:
                    loop = asyncio.get_event_loop()
                    asyncio.ensure_future(self._server._on_message(data, addr))
                except Exception:
                    pass

        def error_received(self, exc: Exception) -> None:
            """Log a transport-level error reported by asyncio.

            Args:
                exc: The exception that triggered the callback.
            """
            logger.error(f"UDP error: {exc}")

    async def send(self, data: bytes, addr: tuple[str, int]) -> None:
        """Send a single datagram to the supplied address.

        No-op when the transport has not been created yet.

        Args:
            data: Payload bytes to transmit.
            addr: ``(host, port)`` destination tuple.
        """
        if self._transport:
            self._transport.sendto(data, addr)

    async def _run_server(self) -> None:
        """Bind the UDP transport and keep the loop alive.

        Creates a datagram endpoint on ``self._host`` / ``self._port``
        using :class:`_UDPProtocol` and stores the transport/protocol
        handles on the instance. The coroutine returns immediately so
        the caller can park the event loop with ``run_forever`` and
        keep the socket listening indefinitely.
        """
        loop = asyncio.get_running_loop()
        self._protocol = self._UDPProtocol(self)
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: self._protocol,
            local_addr=(self._host, self._port),
        )
        self._running = True
        logger.info(f"UDP server listening on {self._host}:{self._port}")

    def start(self) -> None:
        """Launch the UDP server on a dedicated daemon thread.

        The thread installs a fresh asyncio event loop, runs
        ``_run_server`` to bind the socket, and parks the loop with
        ``run_forever`` so it keeps dispatching datagrams. Already
        running servers are left as-is.
        """
        if self._running:
            return

        def target():
            """Thread entry point: bind the socket then park the loop.

            Builds a dedicated loop, drives ``_run_server`` to bind the
            datagram transport, then enters ``run_forever`` so the
            transport keeps delivering incoming datagrams until the
            thread is torn down by :meth:`stop`.
            """
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_server())
            loop.run_forever()

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the UDP server.

        Closes the underlying ``asyncio.DatagramTransport`` so the
        thread's ``run_forever`` loop eventually exits. The
        ``_running`` flag is reset to allow a subsequent ``start``.
        """
        self._running = False
        if self._transport:
            self._transport.close()
        logger.info("UDP server stopped")

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

logger = logging.getLogger("rivex.grpc")


class GRPCServer:
    """gRPC server running in a separate thread.

    Usage::

        server = GRPCServer(port=50051)
        server.add_service(MyServiceServicer())
        server.start()

    Or via app convenience method::

        app.include_grpc_service("/proto/myservice.proto", MyServiceServicer())
    """

    def __init__(self, port: int = 50051, max_workers: int = 10, credentials: Any = None):
        self._port = port
        self._max_workers = max_workers
        self._credentials = credentials
        self._server = None
        self._thread: threading.Thread | None = None
        self._services: list[tuple] = []
        self._running = False

    def add_service(self, service_class: type, implementation: Any = None) -> None:
        """Register a generated gRPC service class and its implementation.

        Appends the pair to the internal service queue so the service is
        bound to the server when ``start`` is called. If ``service_class``
        exposes ``add_to_server``, ``start`` will dispatch the binding to it,
        otherwise the implementation is treated as a stand-alone servicer.

        Args:
            service_class: The generated servicer class (typically the
                object produced by ``grpc.protos`` plus ``grpc.protos``).
                Pass ``None`` when only an implementation is available.
            implementation: An instance of the servicer whose methods
                implement the gRPC service. May be ``None`` when only
                the class is being registered.
        """
        self._services.append((service_class, implementation))

    def add_servicer(self, servicer: Any) -> None:
        """Register a servicer instance whose class has no explicit ``add_to_server``.

        Use it as a convenience for protocols where the servicer carries the
        gRPC bindings on its own class.

        Args:
            servicer: An instance implementing the gRPC service methods.
        """
        self._services.append((None, servicer))

    def start(self) -> None:
        """Bind the registered services and bind to the configured port.

        Imports the ``grpc`` package, builds a ``grpc.server`` with a
        thread-pool executor, dispatches each registered service to the
        server, attaches either a secure or insecure port depending on
        whether ``credentials`` were supplied, and finally starts the
        underlying gRPC server. Repeated calls are a no-op once the
        server is running. The method swallows missing-grpc environments
        with a logged error rather than raising.
        """
        if self._running:
            return

        try:
            import grpc
            from concurrent import futures
        except ImportError:
            logger.error("grpc library is required. Install with: pip install grpcio")
            return

        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=self._max_workers))

        for service_cls, impl in self._services:
            if service_cls and hasattr(service_cls, "add_to_server"):
                try:
                    service_cls.add_to_server(impl, self._server)
                except Exception as e:
                    logger.warning(f"Could not add service {service_cls}: {e}")
            elif impl:
                self._add_servicer_from_impl(impl)

        if self._credentials:
            self._server.add_secure_port(f"[::]:{self._port}", self._credentials)
        else:
            self._server.add_insecure_port(f"[::]:{self._port}")

        self._server.start()
        self._running = True
        logger.info(f"gRPC server started on port {self._port}")

    def _add_servicer_from_impl(self, impl: Any) -> None:
        """Bind a bare servicer instance to the underlying gRPC server.

        Prefers ``impl.add_to_server`` when the instance carries its own
        bindings; otherwise logs a debug message so the rest of the start
        sequence can continue. All exceptions are caught and downgraded
        to debug logging because missing bindings are non-fatal here.

        Args:
            impl: The servicer instance previously added via
                ``add_servicer`` (or via ``add_service`` whose class had
                no ``add_to_server``).
        """
        try:
            import grpc
            proto_module = getattr(impl, "__module__", "")
            servicer_name = type(impl).__name__
            if hasattr(impl, "add_to_server"):
                impl.add_to_server(self._server)
            else:
                logger.debug(f"Servicer {servicer_name} has no add_to_server method")
        except Exception as e:
            logger.debug(f"Could not auto-register servicer: {e}")

    def stop(self, graceful: bool = True, timeout: float = 5.0) -> None:
        """Shut down the underlying gRPC server.

        Forwards to ``grpc.Server.stop``. When ``graceful`` is true, in-flight
        RPCs are allowed to complete within ``timeout`` seconds before the
        server is forcibly closed; otherwise the server is terminated
        immediately. The internal ``_running`` flag is reset so a subsequent
        ``start`` call can re-bind the port.

        Args:
            graceful: When true, allow in-flight RPCs to finish first.
            timeout: Maximum number of seconds to wait for graceful
                shutdown before forcing the server closed.
        """
        if self._server:
            if graceful:
                self._server.stop(timeout)
            else:
                self._server.stop(None)
            self._running = False
            logger.info("gRPC server stopped")

    def run_in_thread(self) -> None:
        """Start the gRPC server on a dedicated background thread.

        The thread installs its own asyncio event loop and invokes
        ``start`` so the caller does not have to manage a loop themselves.
        The thread is marked daemon so it will not block process exit.
        """
        def target():
            """Bootstrap a fresh asyncio loop and invoke ``self.start``.

            Used as the runnable for the daemon thread spawned by
            ``run_in_thread``. Each thread gets its own loop so that
            background asyncio primitives do not collide with the main
            loop of the host process.
            """
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.start()

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def wait_for_termination(self) -> None:
        """Block the current thread until the underlying server terminates.

        Forwards to ``grpc.Server.wait_for_termination``. Has no effect when
        the server was never started.
        """
        if self._server:
            self._server.wait_for_termination()


class GRPCClient:
    """gRPC client for making RPC calls from route handlers.

    Usage::

        client = GRPCClient(target="localhost:50051")
        response = await client.call(method="SayHello", request={"name": "World"})
    """

    def __init__(self, target: str = "localhost:50051", credentials: Any = None):
        self._target = target
        self._credentials = credentials
        self._channel = None

    async def _get_channel(self):
        """Lazily build and cache the asyncio gRPC channel for ``target``.

        Returns the cached channel on subsequent invocations so callers
        can issue many ``call`` operations over the same connection.

        Returns:
            The active ``grpc.aio.Channel`` instance.

        Raises:
            ImportError: When the optional ``grpc`` dependency is not
                installed in the current environment.
        """
        if self._channel is not None:
            return self._channel
        try:
            import grpc
            if self._credentials:
                self._channel = grpc.aio.secure_channel(self._target, self._credentials)
            else:
                self._channel = grpc.aio.insecure_channel(self._target)
            return self._channel
        except ImportError:
            raise ImportError("grpc library is required.")

    async def call(self, stub_class: type, method: str, request: Any) -> Any:
        """Issue a unary RPC against the cached channel.

        Resolves (and caches) the channel, instantiates ``stub_class`` with
        it, locates the named ``method`` attribute on the stub and awaits
        it with ``request`` as the sole argument.

        Args:
            stub_class: The generated stub class (typically obtained via
                ``grpc.protos`` plus ``grpc.protos``).
            method: Name of the RPC method exposed by the stub.
            request: The protobuf message (or compatible object) to send.

        Returns:
            The deserialized response protobuf returned by the server.

        Raises:
            ValueError: When ``method`` is not present on ``stub_class``.
        """
        channel = await self._get_channel()
        stub = stub_class(channel)
        rpc_method = getattr(stub, method, None)
        if rpc_method is None:
            raise ValueError(f"Method '{method}' not found on stub {stub_class.__name__}")
        return await rpc_method(request)

    async def close(self) -> None:
        """Close the cached channel and reset the internal handle.

        Safe to call multiple times; once closed, the next ``call`` will
        transparently rebuild the channel on demand.
        """
        if self._channel:
            await self._channel.close()
            self._channel = None

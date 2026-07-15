from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

logger = logging.getLogger("rivex.grpc")


class GrpcServer:
    """gRPC server running in a separate thread.

    Usage::

        server = GrpcServer(port=50051)
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
        self._services.append((service_class, implementation))

    def add_servicer(self, servicer: Any) -> None:
        self._services.append((None, servicer))

    def start(self) -> None:
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
        if self._server:
            if graceful:
                self._server.stop(timeout)
            else:
                self._server.stop(None)
            self._running = False
            logger.info("gRPC server stopped")

    def run_in_thread(self) -> None:
        def target():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.start()

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def wait_for_termination(self) -> None:
        if self._server:
            self._server.wait_for_termination()


class GrpcClient:
    """gRPC client for making RPC calls from route handlers.

    Usage::

        client = GrpcClient(target="localhost:50051")
        response = await client.call(method="SayHello", request={"name": "World"})
    """

    def __init__(self, target: str = "localhost:50051", credentials: Any = None):
        self._target = target
        self._credentials = credentials
        self._channel = None

    async def _get_channel(self):
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
        channel = await self._get_channel()
        stub = stub_class(channel)
        rpc_method = getattr(stub, method, None)
        if rpc_method is None:
            raise ValueError(f"Method '{method}' not found on stub {stub_class.__name__}")
        return await rpc_method(request)

    async def close(self) -> None:
        if self._channel:
            await self._channel.close()
            self._channel = None

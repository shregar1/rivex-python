"""
Plugin registry for video frame processors.

``ProcessorRegistry`` — a formal ``register_processor(name, factory)``
API that lets third-party code add custom video frame transformers
by name.

Usage::

    from rivex_adapter.webrtc.processor_registry import registry

    # Register a custom processor
    @registry.register("cartoonize")
    def cartoonize(frame):
        # ... apply effect ...
        return frame

    # Later, create by name
    processor = registry.create("cartoonize")

    # List available processors
    for name in registry.list_processors():
        print(name)
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from rivex_adapter.webrtc.media_pipeline import (
    VideoCompositor,
    FrameOverlay,
    GrayscaleTransformer,
    MirrorTransformer,
    ResizeTransformer,
    RotationTransformer,
)
from rivex_adapter.webrtc.core import logger


class ProcessorFactory:
    """Factory that wraps a callable as a processor."""

    def __init__(self, name: str, factory: Callable, description: str = ""):
        self.name = name
        self._factory = factory
        self.description = description

    def create(self, **kwargs) -> Any:
        """Instantiate the processor with optional kwargs."""
        if kwargs:
            return self._factory(**kwargs)
        return self._factory()


class ProcessorRegistry:
    """Global registry of named video frame processors.

    Built-in processors are registered automatically:
    - ``grayscale``
    - ``mirror``
    - ``resize``
    - ``rotate``
    - ``overlay``
    - ``compositor``
    """

    def __init__(self):
        self._processors: dict[str, ProcessorFactory] = {}
        self._register_builtin()

    def register(
        self,
        name: str,
        factory: Callable | None = None,
        description: str = "",
    ) -> Callable:
        """Register a processor factory.

        Can be used as a decorator::

            @registry.register("blur")
            def blur(frame): ...

        Or directly::

            registry.register("blur", blur_factory)
        """
        if factory is None:
            def decorator(fn: Callable) -> Callable:
                self._processors[name] = ProcessorFactory(name, fn, description)
                return fn
            return decorator

        self._processors[name] = ProcessorFactory(name, factory, description)
        return factory

    def create(self, name: str, **kwargs) -> Any:
        """Create a processor instance by name.

        Raises:
            KeyError: If the name is not registered.
        """
        if name not in self._processors:
            raise KeyError(f"Unknown processor: {name}. Available: {list(self._processors.keys())}")
        return self._processors[name].create(**kwargs)

    def list_processors(self) -> list[str]:
        """Return all registered processor names."""
        return list(self._processors.keys())

    def get_info(self, name: str) -> ProcessorFactory | None:
        """Get metadata for a registered processor."""
        return self._processors.get(name)

    def unregister(self, name: str) -> None:
        """Remove a processor from the registry."""
        self._processors.pop(name, None)

    def _register_builtin(self) -> None:
        builtins: list[tuple[str, type | Callable, str]] = [
            ("grayscale", GrayscaleTransformer, "Convert frame to grayscale"),
            ("mirror", MirrorTransformer, "Mirror frame horizontally"),
            ("resize", ResizeTransformer, "Resize frame to given dimensions"),
            ("rotate", RotationTransformer, "Rotate frame by 90/180/270 degrees"),
            ("overlay", FrameOverlay, "Overlay an image on the frame"),
            ("compositor", VideoCompositor, "Compose multiple frames into a grid"),
        ]
        for name, cls, desc in builtins:
            self.register(name, cls, description=desc)


# Global singleton
registry = ProcessorRegistry()

__all__ = [
    "ProcessorRegistry",
    "ProcessorFactory",
    "registry",
]

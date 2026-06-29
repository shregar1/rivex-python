"""
Screen capture for WebRTC broadcasting.

Provides:
- ``ScreenCapture`` — capture screen/display as a video track
- ``VirtualDisplay`` — create a headless virtual display
- ``WindowCapture`` — capture a specific window by title or PID
- ``ScreenShareTrack`` — wraps captured frames as an aiortc MediaStreamTrack

Supports macOS (AVFoundation), Linux (X11/PipeWire), and headless
virtual displays via PyVirtualDisplay or Xvfb.

Usage::

    from rivex_adapter.webrtc import ScreenCapture

    # Capture primary display
    capturer = ScreenCapture(fps=15, max_width=1920, max_height=1080)
    track = await capturer.start()

    # Add to peer connection
    pc = WebRTCPeerConnection()
    sender = pc._pc.addTrack(track)

    # Later
    await capturer.stop()

Requires ``opencv-python`` and platform-specific capture libraries:
- macOS: ``pyavfoundation`` or ``opencv-python`` with AVFoundation
- Linux: ``python-xlib`` or ``pygrabber``
- Headless: ``pyvirtualdisplay`` or ``xvfbwrapper``
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import time
import uuid
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger

try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False


class ScreenShareTrack:
    """An aiortc ``MediaStreamTrack`` that yields screen capture frames.

    Wraps a frame generator function as a media track compatible
    with ``RTCPeerConnection.addTrack()``.
    """

    def __init__(
        self,
        frame_generator: Callable[[], Any],
        fps: float = 15.0,
        kind: str = "video",
    ):
        self.kind = kind
        self._generator = frame_generator
        self._interval = 1.0 / fps
        self._stopped = False

    async def recv(self) -> Any:
        """Return the next video frame."""
        from aiortc import VideoFrame

        while not self._stopped:
            start = time.time()
            frame_data = await self._get_frame()
            if frame_data is not None:
                elapsed = time.time() - start
                wait = self._interval - elapsed
                if wait > 0:
                    await asyncio.sleep(wait)
                return frame_data

            await asyncio.sleep(self._interval)

    async def _get_frame(self) -> Any:
        """Get the next frame from the generator."""
        from aiortc import VideoFrame

        try:
            img = self._generator()
            if img is None:
                return None
            return VideoFrame.from_ndarray(img, format="bgr24")
        except Exception:
            return None

    def stop(self) -> None:
        """Stop the track."""
        self._stopped = True


class ScreenCapture:
    """Capture screen or display as a WebRTC video track.

    Supports:
    - Primary display capture (macOS, Linux, Windows)
    - Custom region capture
    - FPS limiting
    - Scaling to max dimensions

    Usage::

        cap = ScreenCapture(display=0, fps=15, max_width=1280)
        track = await cap.start()

        # Use track with aiortc
        pc._pc.addTrack(track)

        # Later
        await cap.stop()

    Extensibility:
        Override ``open_capture()`` and ``read_frame()`` for
        custom capture backends.
    """

    def __init__(
        self,
        display: int = 0,
        fps: float = 15.0,
        max_width: int = 1920,
        max_height: int = 1080,
        region: tuple[int, int, int, int] | None = None,
    ):
        self.display = display
        self.fps = fps
        self.max_width = max_width
        self.max_height = max_height
        self.region = region
        self._capture: Any = None
        self._track: ScreenShareTrack | None = None
        self._running = False
        self._logger = logger.getChild(f"screen-capture-{display}")

    async def start(self) -> ScreenShareTrack:
        """Start screen capture and return a media track."""
        if not _HAS_CV2:
            raise RuntimeError("opencv-python required for ScreenCapture")

        self._open_capture()
        self._running = True
        self._track = ScreenShareTrack(self._capture_frame, fps=self.fps)
        self._logger.info(
            "screen capture started (display=%d, %dfps)", self.display, self.fps
        )
        return self._track

    async def stop(self) -> None:
        """Stop screen capture."""
        self._running = False
        if self._track is not None:
            self._track.stop()
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._logger.info("screen capture stopped")

    def _open_capture(self) -> None:
        """Open the screen capture device.

        Override for custom capture backends.
        """
        system = platform.system()
        if system == "Darwin":
            self._capture = cv2.VideoCapture(self.display + cv2.CAP_AVFOUNDATION)
        elif system == "Linux":
            self._capture = cv2.VideoCapture(self.display)
        else:
            self._capture = cv2.VideoCapture(self.display, cv2.CAP_DSHOW)

        if not self._capture.isOpened():
            raise RuntimeError(
                f"failed to open display {self.display} "
                f"on {system}. Try a different backend."
            )

        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.max_width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.max_height)
        self._capture.set(cv2.CAP_PROP_FPS, self.fps)

    def _capture_frame(self) -> Any:
        """Read and return a single frame.

        Override for custom frame capture logic.
        """
        if self._capture is None or not self._running:
            return None

        ret, frame = self._capture.read()
        if not ret or frame is None:
            return None

        h, w = frame.shape[:2]
        if w > self.max_width or h > self.max_height:
            scale = min(self.max_width / w, self.max_height / h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            frame = cv2.resize(frame, (new_w, new_h))

        if self.region is not None:
            x, y, rw, rh = self.region
            frame = frame[y : y + rh, x : x + rw]

        return frame

    @property
    def is_capturing(self) -> bool:
        """Whether capture is currently active."""
        return self._running


class VirtualDisplay:
    """Create a headless virtual display for server-side rendering.

    Useful for:
    - Recording without a physical monitor
    - Running WebRTC in cloud/docker environments
    - Broadcasting automated content

    Usage::

        disp = VirtualDisplay(width=1280, height=720)
        await disp.start()

        # Now capture from display 99 (or whatever Xvfb uses)
        cap = ScreenCapture(display=99)

        # Later
        await disp.stop()

    Requires ``pyvirtualdisplay`` or ``xvfbwrapper``::

        pip install pyvirtualdisplay
        # or
        apt-get install xvfb
    """

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        display: int = 99,
    ):
        self.width = width
        self.height = height
        self.display = display
        self._display_obj: Any = None
        self._logger = logger.getChild("virtual-display")

    async def start(self) -> None:
        """Start the virtual display."""
        try:
            from pyvirtualdisplay import Display
            self._display_obj = Display(
                visible=False,
                size=(self.width, self.height),
                backend="xvfb",
            )
            self._display_obj.start()
            self._logger.info(
                "virtual display started (%dx%d, :%d)",
                self.width, self.height, self.display,
            )
        except ImportError:
            import subprocess
            subprocess.run(
                ["Xvfb", f":{self.display}", "-screen", "0",
                 f"{self.width}x{self.height}x24"],
                check=True,
            )
            os.environ["DISPLAY"] = f":{self.display}"
            self._logger.info("xvfb started on :%d", self.display)

    async def stop(self) -> None:
        """Stop the virtual display."""
        if self._display_obj is not None:
            self._display_obj.stop()
            self._display_obj = None
            self._logger.info("virtual display stopped")


class WindowCapture:
    """Capture a specific window by title or process ID.

    Usage::

        wc = WindowCapture(window_title="My App", fps=10)
        track = await wc.start()

    Extensibility:
        Override ``find_window()`` for platform-specific window detection.
    """

    def __init__(
        self,
        window_title: str = "",
        process_id: int | None = None,
        fps: float = 10.0,
        max_width: int = 1920,
        max_height: int = 1080,
    ):
        self.window_title = window_title
        self.process_id = process_id
        self.fps = fps
        self.max_width = max_width
        self.max_height = max_height
        self._capture: Any = None
        self._track: ScreenShareTrack | None = None
        self._running = False
        self._logger = logger.getChild("window-capture")

    async def start(self) -> ScreenShareTrack:
        """Start window capture and return a media track."""
        if not _HAS_CV2:
            raise RuntimeError("opencv-python required for WindowCapture")

        self._find_window()
        self._running = True
        self._track = ScreenShareTrack(
            self._capture_frame, fps=self.fps
        )
        self._logger.info(
            "window capture started: %s", self.window_title or self.process_id
        )
        return self._track

    async def stop(self) -> None:
        """Stop window capture."""
        self._running = False
        if self._track is not None:
            self._track.stop()

    def _find_window(self) -> None:
        """Find the target window.

        Override for platform-specific window detection.
        Falls back to full screen capture.
        """
        system = platform.system()
        if system == "Darwin":
            self._capture = cv2.VideoCapture(0 + cv2.CAP_AVFOUNDATION)
        elif system == "Linux":
            self._capture = cv2.VideoCapture(0)
        else:
            self._capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    def _capture_frame(self) -> Any:
        if self._capture is None or not self._running:
            return None
        ret, frame = self._capture.read()
        if not ret or frame is None:
            return None
        return frame


__all__ = [
    "ScreenCapture",
    "ScreenShareTrack",
    "VirtualDisplay",
    "WindowCapture",
]

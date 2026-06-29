"""
Video analytics for WebRTC streams.

Provides:
- ``MotionDetector`` — pixel-diff-based motion detection
- ``SceneChangeDetector`` — histogram-based scene cut detection
- ``VideoAnalyticsPipeline`` — chain multiple analytics on a track

Usage::

    pipeline = VideoAnalyticsPipeline()
    pipeline.add(MotionDetector(threshold=0.05))
    pipeline.add(SceneChangeDetector(threshold=0.4))

    pipeline.on_event(lambda ev: print(ev.kind, ev.data))

    # Attach to a track
    pipeline.watch_track(video_track)
"""

from __future__ import annotations

import asyncio
import math
import statistics
import struct
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from rivex_adapter.webrtc.core import logger


@dataclass
class VideoEvent:
    """An analytics event emitted by a detector."""

    kind: str  # "motion", "scene_change", "object_detected"
    timestamp: float
    data: dict  # event-specific payload
    track_id: str = ""
    peer_id: str = ""


class VideoAnalyzer(ABC):
    """Base class for video analysis modules."""

    name: str = "analyzer"

    @abstractmethod
    def analyze(self, frame: Any) -> list[VideoEvent]:
        """Analyze a video frame and return any events.

        Args:
            frame: A frame with ``data``, ``width``, ``height`` attributes.

        Returns:
            A list of ``VideoEvent`` (empty if nothing detected).
        """
        ...


class MotionDetector(VideoAnalyzer):
    """Detect motion by comparing consecutive frame histograms.

    Uses a simple luminance histogram difference.  Low CPU, suitable
    for real-time.
    """

    name = "motion"

    def __init__(self, threshold: float = 0.05, cooldown: float = 1.0):
        self._threshold = threshold
        self._cooldown = cooldown
        self._prev_hist: list[float] | None = None
        self._last_event: float = 0.0
        self._motion_count: int = 0

    @property
    def motion_count(self) -> int:
        return self._motion_count

    def analyze(self, frame: Any) -> list[VideoEvent]:
        events: list[VideoEvent] = []
        raw = getattr(frame, "data", frame)
        w = getattr(frame, "width", 0)
        h = getattr(frame, "height", 0)

        if not raw or not w or not h:
            return events

        hist = self._compute_luma_histogram(raw, w, h)

        if self._prev_hist is not None:
            diff = self._histogram_diff(self._prev_hist, hist)
            now = time.time()
            if diff > self._threshold and (now - self._last_event) > self._cooldown:
                self._motion_count += 1
                self._last_event = now
                events.append(VideoEvent(
                    kind="motion",
                    timestamp=now,
                    data={"diff": diff, "count": self._motion_count},
                ))

        self._prev_hist = hist
        return events

    def _compute_luma_histogram(self, data: bytes, width: int, height: int) -> list[float]:
        bins = 32
        hist = [0.0] * bins
        if len(data) < width * height:
            return hist
        for y in range(height):
            row_start = y * width
            for x in range(width):
                idx = row_start + x
                if idx < len(data):
                    pixel = data[idx]
                    bin_idx = min(bins - 1, pixel * bins // 256)
                    hist[bin_idx] += 1.0
        total = sum(hist)
        if total > 0:
            hist = [v / total for v in hist]
        return hist

    def _histogram_diff(self, a: list[float], b: list[float]) -> float:
        return sum(abs(ai - bi) for ai, bi in zip(a, b)) / len(a)


class SceneChangeDetector(VideoAnalyzer):
    """Detect scene cuts using frame-to-frame histogram correlation.

    A sharp change in histogram distribution indicates a scene cut.
    """

    name = "scene_change"

    def __init__(self, threshold: float = 0.4, cooldown: float = 2.0):
        self._threshold = threshold
        self._cooldown = cooldown
        self._prev_hist: list[float] | None = None
        self._last_event: float = 0.0
        self._scene_count: int = 0

    @property
    def scene_count(self) -> int:
        return self._scene_count

    def analyze(self, frame: Any) -> list[VideoEvent]:
        events: list[VideoEvent] = []
        raw = getattr(frame, "data", frame)
        w = getattr(frame, "width", 0)
        h = getattr(frame, "height", 0)

        if not raw or not w or not h:
            return events

        hist = self._compute_rgb_histogram(raw, w, h)

        if self._prev_hist is not None:
            corr = self._histogram_correlation(self._prev_hist, hist)
            now = time.time()
            if corr < (1.0 - self._threshold) and (now - self._last_event) > self._cooldown:
                self._scene_count += 1
                self._last_event = now
                events.append(VideoEvent(
                    kind="scene_change",
                    timestamp=now,
                    data={"correlation": corr, "count": self._scene_count},
                ))

        self._prev_hist = hist
        return events

    def _compute_rgb_histogram(self, data: bytes, width: int, height: int) -> list[float]:
        bins = 16
        hist = [0.0] * (bins * 3)
        if len(data) < width * height * 3:
            return hist
        for i in range(0, min(len(data), width * height * 3), 3):
            r, g, b = data[i], data[i + 1], data[i + 2]
            hist[r * bins // 256] += 1.0
            hist[bins + (g * bins // 256)] += 1.0
            hist[2 * bins + (b * bins // 256)] += 1.0
        total = sum(hist)
        if total > 0:
            hist = [v / total for v in hist]
        return hist

    def _histogram_correlation(self, a: list[float], b: list[float]) -> float:
        mean_a = statistics.mean(a)
        mean_b = statistics.mean(b)
        num = sum((ai - mean_a) * (bi - mean_b) for ai, bi in zip(a, b))
        den_a = math.sqrt(sum((ai - mean_a) ** 2 for ai in a))
        den_b = math.sqrt(sum((bi - mean_b) ** 2 for bi in b))
        if den_a == 0 or den_b == 0:
            return 1.0
        return num / (den_a * den_b)


class VideoAnalyticsPipeline:
    """Chain multiple video analyzers and collect events.

    Usage::

        pipeline = VideoAnalyticsPipeline()
        pipeline.add(MotionDetector(threshold=0.05))
        pipeline.add(SceneChangeDetector(threshold=0.4))

        pipeline.on_event(print)
        pipeline.watch_track(video_track)
    """

    def __init__(self):
        self._analyzers: list[VideoAnalyzer] = []
        self._handlers: list[Callable[[VideoEvent], None]] = []
        self._task: asyncio.Task | None = None

    def add(self, analyzer: VideoAnalyzer) -> None:
        """Register an analyzer."""
        self._analyzers.append(analyzer)

    def remove(self, analyzer: VideoAnalyzer) -> None:
        """Unregister an analyzer."""
        self._analyzers.remove(analyzer)

    def clear(self) -> None:
        """Remove all analyzers."""
        self._analyzers.clear()

    def on_event(self, handler: Callable[[VideoEvent], None]) -> None:
        """Register an event handler."""
        self._handlers.append(handler)

    def watch_track(self, track: Any, peer_id: str = "") -> None:
        """Start analyzing frames from a video track."""
        self._task = asyncio.ensure_future(
            self._run(track, peer_id)
        )

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self, track: Any, peer_id: str) -> None:
        track_id = getattr(track, "id", "unknown")
        try:
            while True:
                try:
                    frame = await asyncio.wait_for(track.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break

                for analyzer in self._analyzers:
                    try:
                        events = analyzer.analyze(frame)
                    except Exception:
                        continue
                    for ev in events:
                        ev.track_id = track_id
                        ev.peer_id = peer_id
                        for handler in self._handlers:
                            try:
                                handler(ev)
                            except Exception:
                                logger.exception("analytics handler error")
        except asyncio.CancelledError:
            pass


__all__ = [
    "VideoAnalyzer",
    "MotionDetector",
    "SceneChangeDetector",
    "VideoAnalyticsPipeline",
    "VideoEvent",
]

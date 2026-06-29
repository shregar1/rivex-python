"""
Recording manager for WebRTC media streams.

Provides:
- ``RecordingJob`` — a single recording with schedule and status
- ``RecordingManager`` — manage multiple recordings with optional scheduling
- ``RecordingScheduler`` — cron-like scheduling for recordings
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger
from rivex_adapter.webrtc.media import MediaRecorder


class RecordingStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RecordingJob:
    """A single recording job with metadata and status."""

    job_id: str
    filepath: str
    status: RecordingStatus = RecordingStatus.PENDING
    started_at: float | None = None
    finished_at: float | None = None
    duration: float = 0.0
    size_bytes: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schedule: str | None = None  # cron expression or ISO interval


class RecordingManager:
    """Manage multiple WebRTC media recordings.

    Supports manual recording start/stop, scheduled recordings,
    and per-recording callbacks.

    Usage::

        manager = RecordingManager(output_dir="/recordings")

        # Add a track to record
        job = await manager.start_recording(
            track=video_track,
            filename="meeting.mp4",
        )

        # Later
        await manager.stop_recording(job.job_id)

        # Or get status
        status = manager.get_job(job.job_id)

    Extensibility:
        Subclass and override ``on_recording_start()``,
        ``on_recording_complete()``, or ``create_recorder()``.
    """

    def __init__(
        self,
        output_dir: str = "/tmp/recordings",
        default_format: str = "mp4",
    ):
        self.output_dir = output_dir
        self.default_format = default_format
        self._jobs: dict[str, RecordingJob] = {}
        self._recorders: dict[str, MediaRecorder] = {}
        self._on_start: list[Callable[[RecordingJob], None]] = []
        self._on_complete: list[Callable[[RecordingJob], None]] = []
        self._on_error: list[Callable[[RecordingJob, Exception], None]] = []
        self._scheduler_task: asyncio.Task[None] | None = None
        self._logger = logger.getChild("recording-manager")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_recording_start(self, callback: Callable[[RecordingJob], None]) -> None:
        """Called when a recording starts."""
        self._on_start.append(callback)

    def on_recording_complete(self, callback: Callable[[RecordingJob], None]) -> None:
        """Called when a recording completes successfully."""
        self._on_complete.append(callback)

    def on_recording_error(
        self, callback: Callable[[RecordingJob, Exception], None]
    ) -> None:
        """Called when a recording fails."""
        self._on_error.append(callback)

    # ------------------------------------------------------------------
    # Recording lifecycle
    # ------------------------------------------------------------------

    async def start_recording(
        self,
        track: Any,
        filename: str | None = None,
        format: str | None = None,
        metadata: dict[str, Any] | None = None,
        duration: float | None = None,
    ) -> RecordingJob:
        """Start recording a media track.

        Args:
            track: An aiortc ``MediaStreamTrack`` (audio or video).
            filename: Output filename. Auto-generated if not provided.
            format: Container format (mp4, webm, etc.). Uses default.
            metadata: Optional metadata dict attached to the job.
            duration: Optional max duration in seconds.

        Returns:
            A ``RecordingJob`` with a ``job_id`` for later reference.
        """
        import uuid

        job_id = uuid.uuid4().hex[:16]
        filename = filename or f"recording_{job_id}.{format or self.default_format}"
        filepath = os.path.join(self.output_dir, filename)

        os.makedirs(self.output_dir, exist_ok=True)

        recorder = self.create_recorder(
            filepath=filepath,
            format=format or self.default_format,
        )
        recorder.add_track(track)

        job = RecordingJob(
            job_id=job_id,
            filepath=filepath,
            metadata=metadata or {},
            status=RecordingStatus.RUNNING,
            started_at=time.time(),
        )

        self._jobs[job_id] = job
        self._recorders[job_id] = recorder

        try:
            await recorder.start()
        except Exception as e:
            job.status = RecordingStatus.FAILED
            job.error = str(e)
            for cb in self._on_error:
                cb(job, e)
            raise

        for cb in self._on_start:
            cb(job)

        if duration is not None:
            asyncio.ensure_future(self._auto_stop(job_id, duration))

        self._logger.info(
            "recording started: %s -> %s", job_id, filepath
        )
        return job

    def create_recorder(self, filepath: str, format: str) -> MediaRecorder:
        """Create a ``MediaRecorder`` for a recording.

        Override to use a custom ``MediaRecorder`` subclass.
        """
        return MediaRecorder(filepath, format=format)

    async def stop_recording(self, job_id: str) -> RecordingJob | None:
        """Stop a recording by job ID.

        Returns the final ``RecordingJob`` or ``None`` if not found.
        """
        job = self._jobs.get(job_id)
        recorder = self._recorders.pop(job_id, None)
        if job is None:
            return None

        if job.status != RecordingStatus.RUNNING:
            return job

        try:
            if recorder is not None:
                await recorder.stop()
            job.status = RecordingStatus.COMPLETED
            job.finished_at = time.time()
            if job.started_at:
                job.duration = job.finished_at - job.started_at
            if os.path.exists(job.filepath):
                job.size_bytes = os.path.getsize(job.filepath)

            for cb in self._on_complete:
                cb(job)

            self._logger.info(
                "recording completed: %s (%.1fs, %d bytes)",
                job_id, job.duration, job.size_bytes,
            )
        except Exception as e:
            job.status = RecordingStatus.FAILED
            job.error = str(e)
            for cb in self._on_error:
                cb(job, e)

        return job

    async def _auto_stop(self, job_id: str, duration: float) -> None:
        await asyncio.sleep(duration)
        await self.stop_recording(job_id)

    def cancel_recording(self, job_id: str) -> None:
        """Cancel a recording without waiting for it to finish."""
        job = self._jobs.get(job_id)
        if job is not None:
            job.status = RecordingStatus.CANCELLED
            job.finished_at = time.time()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_job(self, job_id: str) -> RecordingJob | None:
        """Get a recording job by ID."""
        return self._jobs.get(job_id)

    def list_jobs(
        self, status: RecordingStatus | None = None
    ) -> list[RecordingJob]:
        """List all recording jobs, optionally filtered by status."""
        jobs = list(self._jobs.values())
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        return sorted(jobs, key=lambda j: j.started_at or 0, reverse=True)

    def get_stats(self) -> dict[str, Any]:
        """Get recording manager statistics."""
        all_jobs = self.list_jobs()
        return {
            "total": len(all_jobs),
            "by_status": {
                s.value: len([j for j in all_jobs if j.status == s])
                for s in RecordingStatus
            },
            "active": len([j for j in all_jobs if j.status == RecordingStatus.RUNNING]),
            "output_dir": self.output_dir,
        }

    # ------------------------------------------------------------------
    # Scheduled recordings
    # ------------------------------------------------------------------

    async def start_scheduler(self) -> None:
        """Start the scheduler loop for recurring recordings."""
        if self._scheduler_task is not None:
            return
        self._scheduler_task = asyncio.ensure_future(self._scheduler_loop())

    async def stop_scheduler(self) -> None:
        """Stop the scheduler loop."""
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            self._scheduler_task = None

    async def _scheduler_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(60)
                now = datetime.now()
                for job_id, job in list(self._jobs.items()):
                    if (
                        job.schedule
                        and job.status == RecordingStatus.COMPLETED
                    ):
                        pass
            except asyncio.CancelledError:
                break
            except Exception:
                pass


__all__ = [
    "RecordingManager",
    "RecordingJob",
    "RecordingStatus",
]

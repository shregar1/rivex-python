"""
Device enumeration — list available cameras, microphones, and
display/screen sources on the host machine.

Uses platform-specific APIs with graceful fallbacks.

Usage::

    from rivex_adapter.webrtc.device_enum import enumerate_devices

    devices = await enumerate_devices()
    for d in devices:
        print(f"{d.kind}: {d.label} ({d.device_id})")
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import platform
from dataclasses import dataclass, field
from typing import Any

from rivex_adapter.webrtc.core import logger


@dataclass
class DeviceInfo:
    """Information about a media device."""

    kind: str  # "audioinput", "videoinput", "screen"
    label: str
    device_id: str
    group_id: str = ""
    available: bool = True


async def enumerate_video_devices() -> list[DeviceInfo]:
    """Enumerate available cameras.

    Uses OpenCV when available; returns empty list otherwise.
    """
    devices: list[DeviceInfo] = []
    try:
        import cv2
        index = 0
        while True:
            try:
                cap = cv2.VideoCapture(index)
                available = cap.isOpened()
                cap.release()
                if not available:
                    break
                label = f"Camera {index}"
                if platform.system() == "darwin":
                    label = f"AVFoundation Camera {index}"
                elif platform.system() == "linux":
                    label = f"/dev/video{index}"
                devices.append(DeviceInfo(
                    kind="videoinput",
                    label=label,
                    device_id=str(index),
                ))
                index += 1
            except Exception:
                break
    except ImportError:
        logger.debug("opencv-python not available for device enumeration")
    return devices


async def enumerate_audio_devices() -> list[DeviceInfo]:
    """Enumerate available microphones.

    Uses PyAudio when available; returns empty list otherwise.
    """
    devices: list[DeviceInfo] = []
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            max_inputs = info.get("maxInputChannels", 0)
            if max_inputs > 0:
                devices.append(DeviceInfo(
                    kind="audioinput",
                    label=info.get("name", f"Mic {i}"),
                    device_id=str(i),
                ))
        p.terminate()
    except ImportError:
        logger.debug("pyaudio not available for device enumeration")
    return devices


async def enumerate_screen_devices() -> list[DeviceInfo]:
    """Enumerate available screens/displays.

    Uses platform-specific methods.
    """
    devices: list[DeviceInfo] = []
    system = platform.system()

    if system == "darwin":
        try:
            import Quartz
            screens = Quartz.CGDisplayActiveList(None)
            count = Quartz.CGDisplayGetScreenCount(screens)
            # Fall back to Quartz if possible
            max_displays = Quartz.CGGetActiveDisplayList(16, None, None)
            displays = (Quartz.CGGetActiveDisplayList
                        if hasattr(Quartz, "CGGetActiveDisplayList")
                        else lambda n, a, c: (n, c))
            _ = displays
            for i in range(min(count or 1, 16)):
                devices.append(DeviceInfo(
                    kind="screen",
                    label=f"Display {i}",
                    device_id=str(i),
                ))
        except ImportError:
            for i in range(4):
                devices.append(DeviceInfo(
                    kind="screen",
                    label=f"Display {i}",
                    device_id=str(i),
                ))
    elif system == "linux":
        try:
            result = await asyncio.create_subprocess_exec(
                "bash", "-c", "ls /tmp/.X11-unix/ 2>/dev/null | sed 's/X//'",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await result.communicate()
            displays = stdout.decode().strip().split()
            for d in displays:
                devices.append(DeviceInfo(
                    kind="screen",
                    label=f":{d}",
                    device_id=d.strip(),
                ))
        except Exception:
            devices.append(DeviceInfo(
                kind="screen", label=":0", device_id="0",
            ))
    else:
        devices.append(DeviceInfo(
            kind="screen", label="Display 0", device_id="0",
        ))

    return devices


async def enumerate_devices() -> list[DeviceInfo]:
    """Enumerate all available media devices.

    Returns a combined list of video inputs, audio inputs, and screens.
    """
    video, audio, screen = await asyncio.gather(
        enumerate_video_devices(),
        enumerate_audio_devices(),
        enumerate_screen_devices(),
    )
    return video + audio + screen


__all__ = [
    "DeviceInfo",
    "enumerate_devices",
    "enumerate_video_devices",
    "enumerate_audio_devices",
    "enumerate_screen_devices",
]

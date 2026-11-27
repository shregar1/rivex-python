"""Tests for ``rivex.utilities.timing`` module."""

from __future__ import annotations

import asyncio

import pytest

from rivex.utilities.timing import TimingUtility


class SampleService:
    @TimingUtility.timer("service", operation="sync_op", slow_ms=50)
    def sync_method(self, value: int) -> int:
        return value * 2

    @TimingUtility.timer("service", operation="async_op", slow_ms=50)
    async def async_method(self, value: int) -> int:
        await asyncio.sleep(0.01)
        return value * 3


def test_layer_config():
    TimingUtility.configure_layer("database", slow_ms=200, log_level="DEBUG")
    config = TimingUtility.get_layer_config("database")
    assert config["slow_ms"] == 200
    assert config["log_level"] == "DEBUG"


def test_sync_timer():
    service = SampleService()
    res = service.sync_method(5)
    assert res == 10
    assert getattr(service.sync_method, "__timer_layer__") == "service"


@pytest.mark.asyncio
async def test_async_timer():
    service = SampleService()
    res = await service.async_method(5)
    assert res == 15
    assert getattr(service.async_method, "__timer_layer__") == "service"

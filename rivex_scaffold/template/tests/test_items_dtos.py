"""Smoke tests for the example items slice."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from dtos.items import CreateItemRequest


def test_create_item_request_requires_title() -> None:
    with pytest.raises(PydanticValidationError):
        CreateItemRequest()


def test_create_item_request_valid() -> None:
    payload = CreateItemRequest(title="Buy milk")
    assert payload.title == "Buy milk"
    assert payload.description == ""


def test_create_item_request_trims_whitespace() -> None:
    payload = CreateItemRequest(title="  Trim me  ", description="  desc  ")
    assert payload.title == "Trim me"
    assert payload.description == "desc"

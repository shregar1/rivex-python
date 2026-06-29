"""Smoke tests for the {{resource}} slice."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from dtos.{{resource}} import Create{{model_class}}Request{{request_test_imports}}


def test_create_{{resource}}_request_requires_title() -> None:
    with pytest.raises(PydanticValidationError):
        Create{{model_class}}Request()

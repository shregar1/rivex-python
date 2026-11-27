"""``rivex.utilities.request.form`` — multipart / urlencoded form helpers.

Parsed form fields are stored as ``request_data["form"]`` — a list
of ``dict`` records produced by the multipart parser. Each record
exposes ``name``, ``filename`` (when present), ``content_type``, and
``data`` (raw bytes).
"""

from __future__ import annotations

from typing import Any


class RequestFormUtility:
    """Static helpers for reading and mutating ``request_data["form"]``."""

    @staticmethod
    def get_request_form(request_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the parsed form list (empty list when absent)."""
        form = request_data.get("form")
        return form if isinstance(form, list) else []

    @staticmethod
    def set_request_form(request_data: dict[str, Any], form: list[dict[str, Any]]) -> None:
        """Replace the parsed form list wholesale."""
        request_data["form"] = list(form)

    @staticmethod
    def get_request_form_value(request_data: dict[str, Any], name: str) -> str | None:
        """Return the first form field value matching ``name`` (``None`` when absent)."""
        for field in RequestFormUtility.get_request_form(request_data):
            if field.get("name") == name:
                data = field.get("data")
                return data.decode("utf-8", errors="replace") if isinstance(data, (bytes, bytearray)) else data
        return None

    @staticmethod
    def get_request_form_values(request_data: dict[str, Any], name: str) -> list[str]:
        """Return every form value associated with ``name`` (preserving duplicates)."""
        values: list[str] = []
        for field in RequestFormUtility.get_request_form(request_data):
            if field.get("name") == name:
                data = field.get("data")
                values.append(data.decode("utf-8", errors="replace") if isinstance(data, (bytes, bytearray)) else data)
        return values

    @staticmethod
    def get_request_form_file(request_data: dict[str, Any], name: str) -> dict[str, Any] | None:
        """Return the first upload-shaped form field for ``name`` (``None`` when absent)."""
        for field in RequestFormUtility.get_request_form(request_data):
            if field.get("name") == name and field.get("filename"):
                return field
        return None

    @staticmethod
    def get_request_form_files(request_data: dict[str, Any], name: str) -> list[dict[str, Any]]:
        """Return every upload-shaped form field for ``name``."""
        return [f for f in RequestFormUtility.get_request_form(request_data) if f.get("name") == name and f.get("filename")]


__all__ = ["RequestFormUtility"]

"""Seed codes for ``mime_type_lk``."""

from __future__ import annotations

from typing import Final

from rivex.constants.lookup.abstraction import ILookupConstant


class MimeType(ILookupConstant):
    """Seed codes for the MIME type lookup table."""

    APPLICATION_PDF: Final[str] = "application/pdf"
    APPLICATION_MSWORD: Final[str] = "application/msword"
    APPLICATION_VND_OPENXMLFORMATS_OFFICEDOCUMENT_WORDPROCESSINGML_DOCUMENT: Final[str] = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    APPLICATION_VND_OPENXMLFORMATS_OFFICEDOCUMENT_SPREADSHEETML_SHEET: Final[str] = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    APPLICATION_VND_OPENXMLFORMATS_OFFICEDOCUMENT_PRESENTATIONML_PRESENTATION: Final[str] = (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    APPLICATION_ZIP: Final[str] = "application/zip"
    TEXT_PLAIN: Final[str] = "text/plain"
    TEXT_CSV: Final[str] = "text/csv"
    IMAGE_PNG: Final[str] = "image/png"
    IMAGE_JPEG: Final[str] = "image/jpeg"
    IMAGE_WEBP: Final[str] = "image/webp"
    IMAGE_GIF: Final[str] = "image/gif"
    VIDEO_MP4: Final[str] = "video/mp4"
    APPLICATION_OCTET_STREAM: Final[str] = "application/octet-stream"

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "MimeType"


__all__ = ["MimeType"]

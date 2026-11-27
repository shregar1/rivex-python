"""``rivex.constants.api.media_type`` — MIME type constants.

Backed directly by the native Rust ``RivexMediaType`` PyO3 class.
"""

from __future__ import annotations

from typing import Final

from rivex.constants._rust import RivexMediaType
from rivex.constants.api.abstraction import IAPIConstant


class MediaType(IAPIConstant):
    """MIME type string constants, backed directly by the Rust core."""

    # Application
    APPLICATION_JSON: Final[str] = "application/json"
    APPLICATION_XML: Final[str] = "application/xml"
    APPLICATION_PDF: Final[str] = "application/pdf"
    APPLICATION_ZIP: Final[str] = "application/zip"
    APPLICATION_GZIP: Final[str] = "application/gzip"
    APPLICATION_OCTET_STREAM: Final[str] = "application/octet-stream"
    APPLICATION_X_WWW_FORM_URLENCODED: Final[str] = "application/x-www-form-urlencoded"
    APPLICATION_JAVASCRIPT: Final[str] = "application/javascript"
    APPLICATION_MSWORD: Final[str] = "application/msword"
    APPLICATION_DOCX: Final[str] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    APPLICATION_XLSX: Final[str] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    APPLICATION_PPTX: Final[str] = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    APPLICATION_MSGPACK: Final[str] = "application/msgpack"
    APPLICATION_CBOR: Final[str] = "application/cbor"
    APPLICATION_X_NDJSON: Final[str] = "application/x-ndjson"

    # Text
    TEXT_PLAIN: Final[str] = "text/plain"
    TEXT_PLAIN_UTF8: Final[str] = "text/plain; charset=utf-8"
    TEXT_HTML: Final[str] = "text/html"
    TEXT_CSS: Final[str] = "text/css"
    TEXT_CSV: Final[str] = "text/csv"
    TEXT_XML: Final[str] = "text/xml"
    TEXT_MARKDOWN: Final[str] = "text/markdown"
    TEXT_EVENT_STREAM: Final[str] = "text/event-stream"

    # Multipart
    MULTIPART_FORM_DATA: Final[str] = "multipart/form-data"
    MULTIPART_BYTERANGES: Final[str] = "multipart/byteranges"

    # Image
    IMAGE_PNG: Final[str] = "image/png"
    IMAGE_JPEG: Final[str] = "image/jpeg"
    IMAGE_GIF: Final[str] = "image/gif"
    IMAGE_SVG: Final[str] = "image/svg+xml"
    IMAGE_WEBP: Final[str] = "image/webp"
    IMAGE_ICO: Final[str] = "image/x-icon"

    # Audio & Video
    AUDIO_MPEG: Final[str] = "audio/mpeg"
    AUDIO_WAV: Final[str] = "audio/wav"
    VIDEO_MP4: Final[str] = "video/mp4"
    VIDEO_WEBM: Final[str] = "video/webm"

    DEFAULT_MUTATING_ALLOW_LIST: Final[tuple[str, ...]] = (
        APPLICATION_JSON,
        APPLICATION_X_WWW_FORM_URLENCODED,
        MULTIPART_FORM_DATA,
        TEXT_PLAIN,
    )

    Native = RivexMediaType

    @classmethod
    def is_body_type(cls, mime: str) -> bool:
        """True if the MIME type carries a structured body payload."""
        return RivexMediaType.is_body_type(mime)


__all__ = ["MediaType"]

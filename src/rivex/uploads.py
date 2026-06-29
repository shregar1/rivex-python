from __future__ import annotations

import io
from typing import Any


class UploadFile:
    """File upload object compatible with FastAPI's UploadFile."""

    __slots__ = ("file", "filename", "content_type", "headers", "size")

    def __init__(
        self,
        file: io.BytesIO,
        *,
        filename: str | None = None,
        content_type: str = "application/octet-stream",
        headers: dict[str, str] | None = None,
        size: int | None = None,
    ):
        self.file = file
        self.filename = filename
        self.content_type = content_type
        self.headers = headers or {}
        self.size = size

    async def read(self, size: int = -1) -> bytes:
        return self.file.read(size)

    async def write(self, data: bytes) -> None:
        self.file.write(data)

    async def seek(self, offset: int) -> None:
        self.file.seek(offset)

    async def close(self) -> None:
        self.file.close()

    def __repr__(self) -> str:
        return f"UploadFile(filename={self.filename!r}, content_type={self.content_type!r})"


class File:
    """Marker default for file upload parameters."""

    __slots__ = ("default", "description", "example", "examples")

    def __init__(
        self,
        default: Any = ...,
        *,
        description: str | None = None,
        example: Any = None,
        examples: list[Any] | None = None,
    ):
        self.default = default
        self.description = description
        self.example = example
        self.examples = examples


class Form:
    """Marker default for a single form field — or, when paired with a
    DTO type hint, the whole multipart envelope minus any
    :class:`UploadFile` parts.

    Used two ways:

    1. **Single scalar form field** —

       .. code-block:: python

           async def handler(name: str = Form(min_length=1)): ...

    2. **DTO bound to the multipart body, alongside file uploads** —
       (this is the canonical recipe for the metadata + binary file
       case; see :class:`MultipartBody` for an alias whose name reads
       more naturally in that context)

       .. code-block:: python

           class CreateModel(BaseModel):
               name: str
               category: str

           async def upload_model(
               payload: CreateModel = Form(),
               file: UploadFile = File(),
           ):
               # payload is a validated CreateModel from the form fields.
               # file is the binary upload (extra multipart fields the
               # DTO doesn't declare are ignored).
               ...

       The handler receives a fully-validated DTO from the multipart
       string fields *and* the binary upload as a separate
       :class:`UploadFile` — no base64, no JSON-in-multipart hack.
    """

    __slots__ = (
        "default",
        "alias",
        "title",
        "description",
        "example",
        "examples",
        "min_length",
        "max_length",
        "pattern",
        "gt",
        "ge",
        "lt",
        "le",
    )

    def __init__(
        self,
        default: Any = ...,
        *,
        alias: str | None = None,
        title: str | None = None,
        description: str | None = None,
        example: Any = None,
        examples: list[Any] | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        pattern: str | None = None,
        gt: float | None = None,
        ge: float | None = None,
        lt: float | None = None,
        le: float | None = None,
    ):
        self.default = default
        self.alias = alias
        self.title = title
        self.description = description
        self.example = example
        self.examples = examples
        self.min_length = min_length
        self.max_length = max_length
        self.pattern = pattern
        self.gt = gt
        self.ge = ge
        self.lt = lt
        self.le = le

    @property
    def required(self) -> bool:
        return self.default is ...


# ``MultipartBody`` reads more naturally than ``Form`` when the
# annotation is a DTO that consumes the multipart envelope's string
# fields alongside one or more :class:`File` uploads.  Behaviour is
# identical to :class:`Form` — the same ``form_model`` extraction
# strategy runs — so existing code that uses ``Form()`` for the DTO
# slot keeps working unchanged.
MultipartBody = Form


def parse_multipart(body: bytes, content_type: str) -> dict[str, list[Any]]:
    """Parse multipart/form-data body into a dict of field name → values."""
    try:
        from rivex._compat import HAS_CORE
        from rivex._compat import rc as _rc

        if not HAS_CORE or not hasattr(_rc, "parse_multipart"):
            raise ImportError
        raw_fields = _rc.parse_multipart(content_type, body)
        fields: dict[str, list[Any]] = {}
        for field in raw_fields:
            name = field["name"]
            filename = field.get("filename")
            data = field["data"]
            if filename is not None:
                ct = field.get("content_type") or "application/octet-stream"
                upload = UploadFile(
                    file=io.BytesIO(data),
                    filename=filename,
                    content_type=ct,
                    size=len(data),
                )
                fields.setdefault(name, []).append(upload)
            else:
                fields.setdefault(name, []).append(data.decode("utf-8", errors="replace"))
        return fields
    except (ImportError, ValueError):
        # Rust multipart parser rejects non-UTF-8 file bodies; use Python fallback.
        pass

    boundary = _extract_boundary(content_type)
    if not boundary:
        return {}

    boundary_bytes = f"--{boundary}".encode()
    parts = body.split(boundary_bytes)

    fields = {}
    for part in parts:
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue

        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            continue

        header_block = part[:header_end].decode("utf-8", errors="replace")
        field_body = part[header_end + 4 :]
        if field_body.endswith(b"\r\n"):
            field_body = field_body[:-2]

        disposition = _parse_content_disposition(header_block)
        field_name = disposition.get("name")
        if not field_name:
            continue

        filename = disposition.get("filename")
        if filename is not None:
            ct = _parse_header_value(header_block, "content-type") or "application/octet-stream"
            upload = UploadFile(
                file=io.BytesIO(field_body),
                filename=filename,
                content_type=ct,
                size=len(field_body),
            )
            fields.setdefault(field_name, []).append(upload)
        else:
            fields.setdefault(field_name, []).append(field_body.decode("utf-8", errors="replace"))

    return fields


def _extract_boundary(content_type: str) -> str | None:
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("boundary="):
            boundary = part[9:].strip()
            if boundary.startswith('"') and boundary.endswith('"'):
                boundary = boundary[1:-1]
            return boundary
    return None


def _parse_content_disposition(header_block: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in header_block.split("\r\n"):
        if "content-disposition" not in line.lower():
            continue
        for param in line.split(";")[1:]:
            param = param.strip()
            if "=" in param:
                key, val = param.split("=", 1)
                key = key.strip().lower()
                val = val.strip().strip('"')
                result[key] = val
    return result


def _parse_header_value(header_block: str, header_name: str) -> str | None:
    target = header_name.lower()
    for line in header_block.split("\r\n"):
        if ":" in line:
            name, value = line.split(":", 1)
            if name.strip().lower() == target:
                return value.strip().split(";")[0].strip()
    return None

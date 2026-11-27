"""``rivex.utilities.validation`` — common input validators.

Every validator raises :class:`ValueError` on a failed check so the
caller can wrap the call in a try/except and surface a 400 response.
"""

from __future__ import annotations

import html
import ipaddress
import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional, Sequence

from rivex.utilities.abstraction import LayeredUtility


class ValidationError(ValueError):
    """Raised by :class:`ValidationUtility` when an input fails its check."""

    pass


class ValidationUtility(LayeredUtility):
    """Field validators used by request DTOs and ORM pre-save hooks."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

    def validate_none(self, value: Any, field_name: str = "field", required: bool = True) -> bool:
        """Return ``True`` when ``value`` is ``None`` (and ``required``); raise otherwise."""
        if value is None:
            if required:
                raise ValidationError(f"{field_name} cannot be null")
            return True
        return False

    def validate_instance(
        self,
        value: Any,
        expected_type: Any,
        field_name: str = "field",
        required: bool = True,
        disallow_bool: bool = False,
    ) -> Any:
        """Return ``value`` if it is an instance of ``expected_type``; raise otherwise."""
        if disallow_bool and isinstance(value, bool):
            suffix = " when provided" if not required else ""
            type_desc = expected_type.__name__ if hasattr(expected_type, "__name__") else str(expected_type)
            raise ValidationError(f"{field_name} must be a valid {type_desc}{suffix}, got bool")
        if not isinstance(value, expected_type):
            suffix = " when provided" if not required else ""
            type_desc = expected_type.__name__ if hasattr(expected_type, "__name__") else str(expected_type)
            raise ValidationError(
                f"{field_name} must be a valid {type_desc}{suffix}, got {type(value).__name__}"
            )
        return value

    def validate_empty(self, value: Any, field_name: str = "field") -> Any:
        """Raise when ``value`` is the empty string or an empty container."""
        if isinstance(value, str):
            if not value.strip():
                raise ValidationError(f"{field_name} cannot be empty")
        elif hasattr(value, "__len__") and len(value) == 0:
            raise ValidationError(f"{field_name} cannot be empty")
        return value

    def validate_regex(self, value: str, pattern: str, field_name: str = "field", message: Optional[str] = None) -> str:
        """Raise when ``value`` does not match ``pattern`` (re.match)."""
        if not re.match(pattern, value):
            err_msg = message or f"{field_name} '{value}' does not match valid pattern"
            raise ValidationError(err_msg)
        return value

    def validate_among(
        self,
        value: Any,
        candidates: Sequence[Any],
        field_name: str = "field",
        class_name: Optional[str] = None,
    ) -> Any:
        """Raise when ``value`` is not in ``candidates``."""
        candidate_set = set(candidates)
        if value not in candidate_set:
            sorted_candidates = sorted(list(candidate_set))
            cls_str = f" for {class_name}" if class_name else ""
            raise ValidationError(
                f"Invalid {field_name} '{value}'{cls_str}. Must be one of: {sorted_candidates}"
            )
        return value

    def validate_urn(self, value: Any, field_name: str = "urn", required: bool = True) -> Optional[str]:
        """Validate that ``value`` is a plain UUID or ULID (no ``urn:`` prefix)."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        v = self.validate_instance(value, str, field_name=field_name, required=required)
        cleaned = self.validate_empty(v.strip(), field_name=field_name)
        if cleaned.lower().startswith("urn:"):
            raise ValidationError(f"{field_name} must be a plain UUID or ULID without 'urn:' prefix, got {value!r}")
        try:
            uuid.UUID(cleaned)
            return cleaned
        except ValueError:
            pass
        try:
            import ulid as _ulid_lib

            _ulid_lib.ULID.from_str(cleaned)
            return cleaned
        except (ValueError, ImportError):
            pass
        raise ValidationError(f"{field_name} '{value}' does not match a valid URN, UUID, or ULID pattern")

    def validate_id(self, value: Any, field_name: str = "id", required: bool = True) -> Optional[int]:
        """Validate a positive integer > 0."""
        v = self.validate_int(value, field_name=field_name, required=required)
        if v is not None and v <= 0:
            raise ValidationError(f"{field_name} must be a positive integer greater than zero")
        return v

    def validate_string(self, value: Any, field_name: str = "string", required: bool = True) -> Optional[str]:
        """Validate a non-empty string."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        v = self.validate_instance(value, str, field_name=field_name, required=required)
        return self.validate_empty(v, field_name=field_name)

    def validate_bool(self, value: Any, field_name: str = "bool", required: bool = False) -> Optional[bool]:
        """Validate a ``bool``."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        return self.validate_instance(value, bool, field_name=field_name, required=required)

    def validate_int(self, value: Any, field_name: str = "int", required: bool = True) -> Optional[int]:
        """Validate a non-bool ``int``."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        return self.validate_instance(value, int, field_name=field_name, required=required, disallow_bool=True)

    def validate_float(self, value: Any, field_name: str = "float", required: bool = True) -> Optional[float]:
        """Validate a non-bool ``float`` (or ``int`` cast to float)."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        v = self.validate_instance(value, (float, int), field_name=field_name, required=required, disallow_bool=True)
        return float(v)

    def validate_decimal(self, value: Any, field_name: str = "decimal", required: bool = True) -> Optional[Decimal]:
        """Validate a ``Decimal``."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        v = self.validate_instance(value, (Decimal, float, int, str), field_name=field_name, required=required, disallow_bool=True)
        try:
            return Decimal(str(v))
        except Exception:
            raise ValidationError(f"{field_name} '{value}' is not a valid decimal")

    def validate_list(self, value: Any, field_name: str = "list", required: bool = True) -> Optional[list]:
        """Validate a ``list``."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        return self.validate_instance(value, list, field_name=field_name, required=required)

    def validate_dict(self, value: Any, field_name: str = "dict", required: bool = True) -> Optional[dict]:
        """Validate a ``dict``."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        return self.validate_instance(value, dict, field_name=field_name, required=required)

    def validate_tuple(self, value: Any, field_name: str = "tuple", required: bool = True) -> Optional[tuple]:
        """Validate a ``tuple``."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        return self.validate_instance(value, tuple, field_name=field_name, required=required)

    def validate_set(self, value: Any, field_name: str = "set", required: bool = True) -> Optional[set]:
        """Validate a ``set``."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        return self.validate_instance(value, set, field_name=field_name, required=required)

    def validate_code(
        self,
        value: Any,
        valid_codes: Optional[List[Any]] = None,
        field_name: str = "code",
        required: bool = True,
        class_name: Optional[str] = None,
    ) -> Optional[str]:
        """Validate a string code from an allowed set."""
        v = self.validate_string(value, field_name=field_name, required=required)
        if v is not None and valid_codes:
            self.validate_among(v, valid_codes, field_name=field_name, class_name=class_name)
        return v

    def validate_datetime(self, value: Any, field_name: str = "datetime", required: bool = True) -> Optional[datetime]:
        """Validate a ``datetime`` or an ISO-8601 string."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            cleaned = self.validate_empty(value, field_name=field_name)
            try:
                return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
            except ValueError:
                raise ValidationError(f"{field_name} '{value}' is not a valid ISO datetime format")
        suffix = " when provided" if not required else ""
        raise ValidationError(
            f"{field_name} must be a datetime or ISO datetime string{suffix}, got {type(value).__name__}"
        )

    def validate_email(self, value: Any, field_name: str = "email", required: bool = True) -> Optional[str]:
        """Validate an email address via the standard regex."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        v = self.validate_instance(value, str, field_name=field_name, required=required)
        cleaned = self.validate_empty(v, field_name=field_name)
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        return self.validate_regex(
            cleaned,
            pattern,
            field_name=field_name,
            message=f"{field_name} '{value}' is not a valid email address",
        )

    def validate_uuid(self, value: Any, field_name: str = "uuid", required: bool = True) -> Optional[str]:
        """Validate a UUID string."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        v = self.validate_instance(value, str, field_name=field_name, required=required)
        cleaned = self.validate_empty(v, field_name=field_name)
        try:
            uuid.UUID(cleaned)
            return cleaned
        except ValueError:
            raise ValidationError(f"{field_name} '{value}' is not a valid UUID")

    def validate_url(self, value: Any, field_name: str = "url", required: bool = True) -> Optional[str]:
        """Validate an http/https URL (or localhost / raw IPv4)."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        v = self.validate_instance(value, str, field_name=field_name, required=required)
        cleaned = self.validate_empty(v, field_name=field_name)
        pattern = (
            r"^(?:http|ftp)s?://(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+"
            r"(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"(?::\d+)?(?:/?|[/?]\S+)$"
        )
        return self.validate_regex(
            cleaned,
            pattern,
            field_name=field_name,
            message=f"{field_name} '{value}' is not a valid URL",
        )

    def validate_ip(self, value: Any, field_name: str = "ip_address", required: bool = True) -> Optional[str]:
        """Validate an IPv4 or IPv6 address."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        v = self.validate_instance(value, str, field_name=field_name, required=required)
        cleaned = self.validate_empty(v, field_name=field_name)
        try:
            ipaddress.ip_address(cleaned)
            return cleaned
        except ValueError:
            raise ValidationError(f"{field_name} '{value}' is not a valid IP address")

    def validate_phone(self, value: Any, field_name: str = "phone", required: bool = True) -> Optional[str]:
        """Validate a phone number in E.164 format (``+`` followed by 1-15 digits)."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        v = self.validate_instance(value, str, field_name=field_name, required=required)
        cleaned = self.validate_empty(v, field_name=field_name)
        pattern = r"^\+?[1-9]\d{1,14}$"
        raw_digits = re.sub(r"[\s\-\(\)]", "", cleaned)
        self.validate_regex(
            raw_digits,
            pattern,
            field_name=field_name,
            message=f"{field_name} '{value}' is not a valid phone number",
        )
        return cleaned

    def validate_iban(self, value: Any, field_name: str = "iban", required: bool = True) -> Optional[str]:
        """Validate an IBAN with mod-97 checksum."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        v = self.validate_instance(value, str, field_name=field_name, required=required)
        cleaned = self.validate_empty(v, field_name=field_name).replace(" ", "").upper()
        if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$", cleaned):
            raise ValidationError(f"{field_name} '{value}' is not a valid IBAN format")
        rearranged = cleaned[4:] + cleaned[:4]
        converted = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
        if int(converted) % 97 != 1:
            raise ValidationError(f"{field_name} '{value}' failed IBAN checksum verification")
        return cleaned

    def format_iban(self, value: Any, field_name: str = "iban") -> str:
        """Group an IBAN into 4-character blocks separated by spaces."""
        v = self.validate_iban(value, field_name=field_name)
        return " ".join(v[i:i + 4] for i in range(0, len(v), 4))

    def validate_ascii(self, value: Any, field_name: str = "string", required: bool = True) -> Optional[str]:
        """Validate that a string is pure ASCII."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        v = self.validate_instance(value, str, field_name=field_name, required=required)
        if not v.isascii():
            raise ValidationError(f"{field_name} must contain only ASCII characters")
        return v

    def validate_luhn(self, value: Any, field_name: str = "number", required: bool = True) -> Optional[str]:
        """Validate a numeric string with the Luhn (mod-10) checksum."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        v = self.validate_instance(value, str, field_name=field_name, required=required)
        digits = [int(c) for c in v if c.isdigit()]
        if not digits:
            raise ValidationError(f"{field_name} must contain digits for Luhn verification")
        checksum = 0
        reverse_digits = digits[::-1]
        for idx, digit in enumerate(reverse_digits):
            if idx % 2 == 1:
                doubled = digit * 2
                checksum += doubled - 9 if doubled > 9 else doubled
            else:
                checksum += digit
        if checksum % 10 != 0:
            raise ValidationError(f"{field_name} '{value}' failed Luhn checksum verification")
        return v

    def sanitize_html(self, value: Any, field_name: str = "html", required: bool = True) -> Optional[str]:
        """HTML-escape a string."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        v = self.validate_instance(value, str, field_name=field_name, required=required)
        return html.escape(v)

    def strip_html_tags(self, value: Any, field_name: str = "html", required: bool = True) -> Optional[str]:
        """Strip all ``<...>`` tags from ``value`` (regex-based, not a full parser)."""
        if self.validate_none(value, field_name=field_name, required=required):
            return None
        v = self.validate_instance(value, str, field_name=field_name, required=required)
        return re.sub(r"<[^>]*>", "", v)

    def validate_json_schema(self, instance: Any, schema: Any, field_name: str = "json") -> Any:
        """Validate against a tiny subset of JSON schema (``type`` only)."""
        if not isinstance(schema, dict):
            raise ValidationError("JSON schema specification must be a dictionary")
        if "type" in schema:
            expected = schema["type"]
            if expected == "object":
                self.validate_dict(instance, field_name=field_name)
            elif expected == "array":
                self.validate_list(instance, field_name=field_name)
            elif expected == "string":
                self.validate_string(instance, field_name=field_name)
            elif expected == "integer":
                self.validate_int(instance, field_name=field_name)
            elif expected == "boolean":
                self.validate_bool(instance, field_name=field_name)
        return instance

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "ValidationUtility"


__all__ = ["ValidationUtility", "ValidationError"]

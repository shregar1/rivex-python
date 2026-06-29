"""Input validation via Rivex Rust validators."""

from __future__ import annotations

from rivex import (
    format_iban,
    is_ascii,
    luhn_check,
    sanitize_html,
    strip_html_tags,
    validate_email,
    validate_iban,
    validate_ip,
    validate_json_schema,
    validate_phone,
    validate_url,
    validate_uuid,
)

from abstractions.utility import IUtility


class ValidationUtility(IUtility):
    """Fast validators backed by ``rivex``."""

    @classmethod
    def name(cls) -> str:
        return "validation"

    def is_valid_email(self, value: str) -> bool:
        return validate_email(value)

    def is_valid_url(self, value: str) -> bool:
        return validate_url(value)

    def is_valid_ip(self, value: str) -> bool:
        return validate_ip(value)

    def is_valid_uuid(self, value: str) -> bool:
        return validate_uuid(value)

    def is_valid_phone(self, value: str) -> bool:
        return validate_phone(value)

    def is_valid_iban(self, value: str) -> bool:
        return validate_iban(value)

    def format_iban(self, value: str) -> str:
        return format_iban(value)

    def is_ascii(self, value: str) -> bool:
        return is_ascii(value)

    def luhn_check(self, value: str) -> bool:
        return luhn_check(value)

    def validate_json_schema(
        self,
        instance: str,
        schema: str,
    ) -> tuple[bool, str | None]:
        return validate_json_schema(instance, schema)

    def sanitize_html(self, value: str) -> str:
        return sanitize_html(value)

    def strip_html_tags(self, value: str) -> str:
        return strip_html_tags(value)

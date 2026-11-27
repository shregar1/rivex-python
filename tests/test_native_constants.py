"""Tests for the new native constants and regex subpackages."""

import pytest
from rivex.constants import (
    ExceptionCode,
    ExceptionMessage,
    ExceptionStatus,
    Header,
    HTTPMethod,
    IAPIConstant,
    IConstant,
    IExceptionConstant,
    InjectionRegex,
    IRegexConstant,
    MediaType,
    PiiRegex,
    SecurityKeyRegex,
)


def test_iconstant_reflection_helpers():
    assert issubclass(HTTPMethod, IAPIConstant)
    assert issubclass(HTTPMethod, IConstant)
    assert "GET" in HTTPMethod.values()
    assert "GET" in HTTPMethod.keys()
    assert HTTPMethod.is_valid("POST") is True
    assert HTTPMethod.is_valid("INVALID_VERB") is False

    assert issubclass(ExceptionCode, IExceptionConstant)
    assert issubclass(ExceptionCode, IConstant)
    assert ExceptionCode.is_valid("BAD_REQUEST") is True

    assert issubclass(ExceptionMessage, IExceptionConstant)
    assert issubclass(ExceptionMessage, IConstant)
    assert ExceptionMessage.is_valid("Bad request syntax or payload") is True

    assert issubclass(IRegexConstant, IConstant)


def test_http_method_query_support():
    assert HTTPMethod.QUERY == "QUERY"
    assert "QUERY" in HTTPMethod.all_methods()
    assert HTTPMethod.parse("QUERY") == "QUERY"
    assert HTTPMethod.is_mutating("QUERY") is False
    assert HTTPMethod.is_mutating("POST") is True


def test_http_method_trace_and_connect():
    assert HTTPMethod.TRACE == "TRACE"
    assert HTTPMethod.CONNECT == "CONNECT"
    assert "TRACE" in HTTPMethod.all_methods()
    assert "CONNECT" in HTTPMethod.all_methods()


def test_media_type_extensions():
    assert MediaType.APPLICATION_JSON == "application/json"
    assert MediaType.APPLICATION_XML == "application/xml"
    assert MediaType.TEXT_PLAIN_UTF8 == "text/plain; charset=utf-8"
    assert MediaType.APPLICATION_MSGPACK == "application/msgpack"
    assert MediaType.is_body_type("application/json") is True
    assert MediaType.is_body_type("text/event-stream") is False


def test_header_extensions():
    assert Header.AUTHORIZATION == "authorization"
    assert Header.CONTENT_TYPE == "content-type"
    assert Header.CONTENT_LENGTH == "content-length"
    assert Header.X_REQUEST_ID == "x-request-id"
    assert Header.TRACEPARENT == "traceparent"
    assert Header.ACCESS_CONTROL_ALLOW_ORIGIN == "access-control-allow-origin"


def test_error_codes_and_status():
    assert ExceptionCode.UNSUPPORTED_MEDIA_TYPE == "UNSUPPORTED_MEDIA_TYPE"
    assert ExceptionCode.PAYLOAD_TOO_LARGE == "PAYLOAD_TOO_LARGE"
    assert ExceptionCode.PROHIBITED_ID_PARAMETER == "PROHIBITED_ID_PARAMETER"
    assert ExceptionCode.MALICIOUS_INPUT_DETECTED == "MALICIOUS_INPUT_DETECTED"
    assert ExceptionStatus.PAYLOAD_TOO_LARGE == 413
    assert ExceptionStatus.UNSUPPORTED_MEDIA_TYPE == 415
    assert ExceptionStatus.METHOD_NOT_ALLOWED == 405
    assert ExceptionStatus.BAD_GATEWAY == 502
    assert ExceptionStatus.BAD_REQUEST == 400


def test_iregex_constant_compile_patterns():
    patterns = IRegexConstant.compile_patterns([r"\d+", r"[a-z]+"])
    assert len(patterns) == 2


def test_security_key_regex():
    assert SecurityKeyRegex.is_sensitive_key("api_key") is True
    assert SecurityKeyRegex.is_sensitive_key("user_password") is True
    assert SecurityKeyRegex.is_sensitive_key("user_name") is False
    assert SecurityKeyRegex.matches_value("sk_live_1234567890123456") is True
    assert SecurityKeyRegex.matches_value("ghp_12345678901234567890") is True
    assert SecurityKeyRegex.matches_value("plain_text") is False


def test_pii_regex():
    assert PiiRegex.is_ssn("123-45-6789") is True
    assert PiiRegex.is_ssn("123456789") is False
    assert PiiRegex.is_card("4111111111111111") is True
    assert PiiRegex.is_card("1234") is False


def test_injection_regex():
    assert InjectionRegex.has_xss("<script>alert(1)</script>") is True
    assert InjectionRegex.has_xss("javascript:alert(1)") is True
    assert InjectionRegex.has_xss("Hello World") is False
    assert InjectionRegex.has_sqli("SELECT * FROM users WHERE id = 1 UNION SELECT 1") is True
    assert InjectionRegex.has_sqli("DROP TABLE users--") is True
    assert InjectionRegex.has_sqli("Normal search text") is False

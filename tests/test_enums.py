"""Tests for the rivex.enums subpackage."""

import pytest

from rivex.constants.api import HTTPMethod
from rivex.constants.auth import AuthRoleConstant, AuthSchemeConstant, AuthTokenConstant
from rivex.constants.observability import (
    LogLevelConstant,
    MetricTypeConstant,
    TraceStateConstant,
)
from rivex.constants.websocket import (
    WebSocketDisconnectConstant,
    WebSocketFrameConstant,
    WebSocketStateConstant,
)
from rivex.enums import (
    APIResult,
    APIStatus,
    AuthScheme,
    ConnectionState,
    DisconnectCode,
    FrameType,
    HTTPMethodEnum,
    IEnum,
    LogLevel,
    MetricType,
    RoleLevel,
    SameSitePolicy,
    TokenType,
    TraceState,
)


def test_ienum_reflection():
    assert issubclass(APIResult, IEnum)
    assert "SUCCESS" in APIResult.values()
    assert "SUCCESS" in APIResult.names()
    assert APIResult.is_valid("SUCCESS") is True
    assert APIResult.is_valid("INVALID") is False
    assert issubclass(APIStatus, IEnum)
    assert APIStatus.OK == 200
    assert APIStatus.is_valid(200) is True
    assert APIStatus.is_valid(999) is False


def test_http_method_enum_built_from_constants():
    assert HTTPMethodEnum.GET.value == HTTPMethod.GET
    assert HTTPMethodEnum.QUERY.value == HTTPMethod.QUERY
    assert HTTPMethodEnum.POST.value == "POST"


def test_auth_enums_built_from_constants():
    assert TokenType.BEARER.value == AuthTokenConstant.BEARER
    assert AuthScheme.BEARER.value == AuthSchemeConstant.BEARER
    assert RoleLevel.ADMIN.value == AuthRoleConstant.ADMIN


def test_observability_enums_built_from_constants():
    assert LogLevel.INFO.value == LogLevelConstant.INFO
    assert MetricType.COUNTER.value == MetricTypeConstant.COUNTER
    assert TraceState.RECORDING.value == TraceStateConstant.RECORDING


def test_websocket_enums_built_from_constants():
    assert FrameType.TEXT.value == WebSocketFrameConstant.TEXT
    assert ConnectionState.OPEN.value == WebSocketStateConstant.OPEN
    assert DisconnectCode.NORMAL.value == WebSocketDisconnectConstant.NORMAL

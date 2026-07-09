from rivex import schemax
from rivex._rust import (
    format_iban,
    hash_argon2,
    hash_bcrypt,
    hash_password,
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
    verify_password,
)
from rivex.applications import FastAPI, Rivex
from rivex.asgi import ASGIAdapter, ASGIWebSocket
from rivex.auth import (
    admin_only,
    authenticated,
    current_user,
    get_user_resolver,
    set_user_resolver,
)
from rivex.background import BackgroundTask, BackgroundTasks
from rivex.broadcast import (
    ChannelLayer,
    Room,
    WebSocketBroadcast,
    WebSocketChannel,
)
from rivex.caching import CacheMiddleware, ETagMiddleware, cached_response
from rivex.concurrency import run_in_threadpool
from rivex.contenttypes import (
    ContentTypeRegistry,
    GenericForeignKey,
    GenericRelation,
    get_content_type,
    get_object,
)
from rivex.context import (
    RequestContext,
    RequestContextMiddleware,
    bind_extra,
    bind_user,
    current_ip,
    current_request_id,
    current_user_agent,
    current_user_id,
    request_context,
)
from rivex.csrf import CSRFMiddleware
from rivex.datastructures import Headers
from rivex.db import DatabaseConfig, DatabasePool, DatabaseRegistry
from rivex.db.automigrate import AutoMigrator
from rivex.db.router import DatabaseRouter, RouterRegistry, using
from rivex.db.transactions import Transaction, atomic
from rivex.debugtoolbar import DebugToolbarMiddleware
from rivex.dependencies import Dependency, Depends
from rivex.email import (
    ConsoleBackend,
    EmailBackend,
    EmailMessage,
    FileBackend,
    SmtpBackend,
    get_email_backend,
    send_email,
)
from rivex.encoders import jsonable_encoder
from rivex.events import (
    Signal,
    request_failed,
    request_finished,
    request_started,
    server_shutdown,
    server_startup,
)
from rivex.exceptions import HTTPException, RequestValidationError, WebSocketDisconnect
from rivex.feeds import AtomFeed, RssFeed, Sitemap, SitemapIndex
from rivex.forms import (
    BooleanField as BooleanField,
)
from rivex.forms import (
    CharField as CharField,
)
from rivex.forms import (
    EmailField as EmailField,
)
from rivex.forms import (
    FormField as FormField,
)
from rivex.forms import (
    IntegerField as IntegerField,
)
from rivex.forms import (
    PasswordField as PasswordField,
)
from rivex.forms import (
    SelectField as SelectField,
)
from rivex.forms import (
    TextAreaField as TextAreaField,
)
from rivex.forms import (
    ValidationError as ValidationError,
)
from rivex.gen import F, JsonBytes, gen
from rivex.gis import (
    GeographyColumn,
    GeometryCollection,
    GeometryColumn,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    SpatialQuery,
    earth_distance,
    haversine_distance,
    to_geojson,
)
from rivex.graphql import GraphQLMiddleware, graphql_mutation, graphql_query
from rivex.grpc import GrpcClient, GrpcServer
from rivex.grpc_web import GrpcWebMiddleware, GrpcWebServer
from rivex.guards import AllowAll, DenyAll, Guard, GuardMiddleware, IsAuthenticated, RequiresRoles
from rivex.health import HealthCheck
from rivex.htmx import (
    HtmxDetails,
    HtmxResponse,
    HXLocation,
    HXPushUrl,
    HXRedirect,
    HXRefresh,
    HXReselect,
    HXRetarget,
    HXSwap,
)
from rivex.http3 import Http3Client, Http3Server
from rivex.i18n import (
    LocaleMiddleware,
    Translations,
    format_currency,
    format_date,
    format_number,
    get_locale,
    gettext,
    ngettext,
    pgettext,
    set_locale,
)
from rivex.jsonrpc import JSONRPCMiddleware, XMLRPCMiddleware
from rivex.jwt import ExpiredTokenError, InvalidTokenError, JWTBearer, JWTError
from rivex.jwt import decode as jwt_decode
from rivex.jwt import encode as jwt_encode
from rivex.management import (
    BaseCommand,
    CommandError,
    discover_commands,
    get_all_commands,
    get_command,
    register_command,
)
from rivex.metrics import Counter, Gauge, Histogram, MetricsMiddleware, MetricsRegistry
from rivex.middleware import (
    AccessLogMiddleware,
    CompressionMiddleware,
    CORSMiddleware,
    GZipMiddleware,
    HTTPSRedirectMiddleware,
    IdempotencyMiddleware,
    IPFilterMiddleware,
    MaxBodySizeMiddleware,
    MethodOverrideMiddleware,
    Middleware,
    RateLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    TimeoutMiddleware,
    TrailingSlashMiddleware,
    TrustedHostMiddleware,
)

# New features
from rivex.middleware_csp import CSPMiddleware
from rivex.mqtt import MQTTBridge
from rivex.negotiation import best_match, parse_accept
from rivex.otel import (
    OpenTelemetryMiddleware,
    configure_otel,
    get_tracer,
    set_tracer,
)
from rivex.pagination import CursorPage, Page, paginate
from rivex.params import Body, Cookie, Header, Path, Query
from rivex.password_reset import PasswordReset, PasswordResetMiddleware
from rivex.permissions import (
    DEFAULT_PERMISSIONS,
    ModelPermission,
    ObjectPermissionBackend,
    Permission,
    RoleBasedBackend,
    User,
    has_permission,
    permission_required,
    register_permission,
)
from rivex.plugins import Plugin
from rivex.problem import (
    ProblemDetail,
    ProblemException,
    ProblemResponse,
    bad_request,
    conflict,
    forbidden,
    internal_error,
    not_found,
    problem_exception_handler,
    unauthorized,
    unprocessable,
)
from rivex.rawsocket import RawTCPServer, UDPBroadcastServer, UnixSocketServer
from rivex.requests import Request
from rivex.responses import (
    EventSourceResponse,
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
    XMLResponse,
)
from rivex.routing import (
    APIRouter,
    Controller,
    RouteGroup,
    Router,
    delete,
    get,
    head,
    options,
    patch,
    post,
    put,
    route,
)
from rivex.scheduler import Scheduler
from rivex.schema import Field, Schema
from rivex.search import (
    ElasticsearchBackend,
    PostgresSearchBackend,
    SearchBackend,
)
from rivex.security import (
    APIKeyCookie,
    APIKeyHeader,
    APIKeyQuery,
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
    OAuth2AuthorizationCodeBearer,
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
    SecurityScopes,
)
from rivex.sentry import (
    SentryMiddleware,
    capture_exception,
    configure_sentry,
    set_extra_context,
    set_user_context,
)
from rivex.serialization import deserialize, serialize, set_serializer
from rivex.serializers import Field as SerializerField
from rivex.serializers import (
    ListSerializer,
    ModelSerializer,
    Serializer,
)
from rivex.sessions import SessionMiddleware
from rivex.settings import Settings
from rivex.social_auth import SocialAuthConfig, SocialAuthMiddleware
from rivex.socketio import (
    SocketIOMiddleware,
    SocketIOServer,
    SocketIOSession,
)
from rivex.static_pipeline import StaticPipeline
from rivex.staticfiles import StaticFiles
from rivex.status import APIStatus, HTTPMethod, HTTPStatus, StatusCode, status
from rivex.structlog import (
    JSONFormatter,
    StructuredAccessLogMiddleware,
    StructuredLogger,
    configure_logging,
)
from rivex.tasks import (
    CeleryTaskQueue,
    RQTaskQueue,
    SimpleTaskQueue,
    Task,
    TaskQueue,
    task,
)
from rivex.templating import Jinja2Templates
from rivex.testing import TestClient
from rivex.throttling import (
    AnonRateThrottle,
    BaseThrottle,
    ScopedRateThrottle,
    ThrottleMiddleware,
    UserRateThrottle,
)
from rivex.tracing import (
    ConsoleSpanExporter,
    OTelSpanExporter,
    Span,
    SpanExporter,
    TracingMiddleware,
    configure_tracing,
)
from rivex.uploads import File, Form, MultipartBody, UploadFile
from rivex.versioning import (
    AcceptHeaderVersioning,
    BaseVersioning,
    HeaderVersioning,
    QueryParamVersioning,
    URLPathVersioning,
    VersionMiddleware,
)
from rivex.viewsets import (
    BrowsableApiMiddleware,
    ListModelMixin,
    ModelViewSet,
    ViewSet,
)
from rivex.viewsets import (
    Router as ViewSetRouter,
)
from rivex.webdav import WebDAVMiddleware
from rivex.webhooks import WebhookGuard, WebhookVerificationError, verify_signature

# WebSocket feature classes — drop-in helpers for common patterns
from rivex.websocket_features import (
    BinaryCodec,
    HeartbeatManager,
    JSONCodec,
    MsgPackCodec,
    MultiServerBackend,
    NATSBackend,
    PresenceTracker,
    RateLimiter,
    ReconnectionHelper,
    RedisPubSubBackend,
    RPCClient,
    RPCServer,
    TypingIndicators,
    WSAuthMiddleware,
    register_codec,
    require_ws_auth,
    rpc_method,
)
from rivex.websockets import WebSocket

# Additional protocols
from rivex.webtransport import (
    WebTransportClient,
    WebTransportServer,
    WebTransportSession,
)
from rivex.ws import ConnectionManager

# Admin dashboard — ``rivex_admin`` is an optional companion
# package.  Users who only want the bare HTTP framework don't pay
# the import cost of the HTMX/Alpine SPA.  Install with
# ``pip install rivex[admin]``.
try:
    from rivex_admin import admin_action, admin_partial  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    admin_action = None  # type: ignore[assignment]
    admin_partial = None  # type: ignore[assignment]

# Native body-type coercion: Pydantic, Schemax, Marshmallow, or raw dict.
# Importing this module never fails — the availability of each backend
# depends on whether the corresponding optional dependency is installed.
from rivex._bodies import (
    SCHEMAS,
    BodySchema,
    body_schema,
    coerce_body,
    is_body_model,
    register_body_schema,
)

__version__ = "0.2.3"
__all__ = [
    # Core
    "Rivex",
    "FastAPI",
    "Router",
    "APIRouter",
    "Controller",
    "RouteGroup",
    "Plugin",
    "route",
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "head",
    "options",
    "Request",
    "Body",
    "Query",
    "Path",
    "Header",
    "Cookie",
    "Schema",
    "Field",
    "Settings",
    "Dependency",
    "Depends",
    "HTTPException",
    "RequestValidationError",
    "WebSocketDisconnect",
    "TestClient",
    "BackgroundTask",
    "BackgroundTasks",
    "CacheMiddleware",
    "ETagMiddleware",
    "cached_response",
    # Database
    "DatabaseConfig",
    "DatabasePool",
    "DatabaseRegistry",
    # Security
    "APIKeyHeader",
    "APIKeyQuery",
    "APIKeyCookie",
    "HTTPAuthorizationCredentials",
    "HTTPBasicCredentials",
    "HTTPBearer",
    "HTTPBasic",
    "OAuth2PasswordBearer",
    "OAuth2AuthorizationCodeBearer",
    "OAuth2PasswordRequestForm",
    "SecurityScopes",
    # Guards
    "Guard",
    "GuardMiddleware",
    "IsAuthenticated",
    "RequiresRoles",
    "AllowAll",
    "DenyAll",
    # Status
    "HTTPMethod",
    "APIStatus",
    "HTTPStatus",
    "StatusCode",
    "status",
    # Responses
    "Response",
    "JSONResponse",
    "HTMLResponse",
    "PlainTextResponse",
    "RedirectResponse",
    "StreamingResponse",
    "EventSourceResponse",
    "FileResponse",
    "XMLResponse",
    # Content negotiation
    "parse_accept",
    "best_match",
    # Encoders
    "jsonable_encoder",
    # Serialization
    "serialize",
    "deserialize",
    "set_serializer",
    # Request context
    "RequestContext",
    "RequestContextMiddleware",
    "request_context",
    "current_user_id",
    "current_ip",
    "current_user_agent",
    "current_request_id",
    "bind_user",
    "bind_extra",
    # Auth decorators
    "authenticated",
    "admin_only",
    "current_user",
    "set_user_resolver",
    "get_user_resolver",
    # Middleware
    "Middleware",
    "MethodOverrideMiddleware",
    "AccessLogMiddleware",
    "CompressionMiddleware",
    "CORSMiddleware",
    "CSRFMiddleware",
    "CacheMiddleware",
    "ETagMiddleware",
    "GZipMiddleware",
    "HTTPSRedirectMiddleware",
    "IdempotencyMiddleware",
    "IPFilterMiddleware",
    "MaxBodySizeMiddleware",
    "RateLimitMiddleware",
    "RequestIdMiddleware",
    "SecurityHeadersMiddleware",
    "SessionMiddleware",
    "TimeoutMiddleware",
    "TrailingSlashMiddleware",
    "TrustedHostMiddleware",
    # Throttling
    "BaseThrottle",
    "AnonRateThrottle",
    "UserRateThrottle",
    "ScopedRateThrottle",
    "ThrottleMiddleware",
    # Pagination
    "Page",
    "CursorPage",
    "paginate",
    # Background tasks
    "BackgroundTask",
    "BackgroundTasks",
    # Caching
    "cached_response",
    # Concurrency
    "run_in_threadpool",
    # Rust-native list generator
    "gen",
    "F",
    "JsonBytes",
    # File uploads
    "UploadFile",
    "File",
    "Form",
    "MultipartBody",
    # Data structures
    "Headers",
    # ASGI
    "ASGIAdapter",
    "ASGIWebSocket",
    # WebSocket
    "WebSocket",
    "ConnectionManager",
    # Static files & templates
    "StaticFiles",
    "Jinja2Templates",
    # HTMX helpers
    "HtmxDetails",
    "HtmxResponse",
    "HXRedirect",
    "HXRefresh",
    "HXLocation",
    "HXSwap",
    "HXRetarget",
    "HXReselect",
    "HXPushUrl",
    # Problem Details (RFC 7807)
    "ProblemDetail",
    "ProblemException",
    "ProblemResponse",
    "problem_exception_handler",
    "not_found",
    "bad_request",
    "unauthorized",
    "forbidden",
    "conflict",
    "unprocessable",
    "internal_error",
    # Events / Signals
    "Signal",
    "request_started",
    "request_finished",
    "request_failed",
    "server_startup",
    "server_shutdown",
    # Structured Logging
    "JSONFormatter",
    "StructuredLogger",
    "StructuredAccessLogMiddleware",
    "configure_logging",
    # Health Checks
    "HealthCheck",
    # JWT
    "jwt_encode",
    "jwt_decode",
    "JWTBearer",
    "JWTError",
    "ExpiredTokenError",
    "InvalidTokenError",
    # Webhooks
    "verify_signature",
    "WebhookGuard",
    "WebhookVerificationError",
    # Metrics
    "Counter",
    "Gauge",
    "Histogram",
    "MetricsRegistry",
    "MetricsMiddleware",
    # Tracing
    "Span",
    "SpanExporter",
    "ConsoleSpanExporter",
    "OTelSpanExporter",
    "TracingMiddleware",
    "configure_tracing",
    # Versioning
    "BaseVersioning",
    "URLPathVersioning",
    "HeaderVersioning",
    "QueryParamVersioning",
    "AcceptHeaderVersioning",
    "VersionMiddleware",
    # Rust-backed hashing + validation (requires rivex-core)
    "hash_password",
    "verify_password",
    "hash_bcrypt",
    "hash_argon2",
    "validate_email",
    "validate_url",
    "validate_ip",
    "validate_uuid",
    "validate_phone",
    "validate_json_schema",
    "validate_iban",
    "format_iban",
    "is_ascii",
    "luhn_check",
    "sanitize_html",
    "strip_html_tags",
    # Pluggable body schemas (Pydantic / Schemax / Marshmallow / raw dict)
    "BodySchema",
    "SCHEMAS",
    "body_schema",
    "coerce_body",
    "is_body_model",
    "register_body_schema",
    # Back-compat re-export of the Schemax shim (deprecated — emits a
    # DeprecationWarning on import so users migrate to ``schemax.idl``).
    "schemax",
    # New features
    "CSPMiddleware",
    "Permission",
    "ModelPermission",
    "User",
    "RoleBasedBackend",
    "ObjectPermissionBackend",
    "register_permission",
    "has_permission",
    "permission_required",
    "DEFAULT_PERMISSIONS",
    "CharField",
    "EmailField",
    "PasswordField",
    "IntegerField",
    "BooleanField",
    "SelectField",
    "TextAreaField",
    "ValidationError",
    "Translations",
    "LocaleMiddleware",
    "set_locale",
    "get_locale",
    "gettext",
    "ngettext",
    "pgettext",
    "format_number",
    "format_date",
    "format_currency",
    "BaseCommand",
    "CommandError",
    "register_command",
    "get_command",
    "get_all_commands",
    "discover_commands",
    "Transaction",
    "atomic",
    "AutoMigrator",
    "DatabaseRouter",
    "RouterRegistry",
    "using",
    "DebugToolbarMiddleware",
    "StaticPipeline",
    "SearchBackend",
    "PostgresSearchBackend",
    "ElasticsearchBackend",
    "TaskQueue",
    "SimpleTaskQueue",
    "CeleryTaskQueue",
    "RQTaskQueue",
    "Task",
    "task",
    "Scheduler",
    "EmailBackend",
    "SmtpBackend",
    "ConsoleBackend",
    "FileBackend",
    "EmailMessage",
    "get_email_backend",
    "send_email",
    "SocialAuthConfig",
    "SocialAuthMiddleware",
    "PasswordReset",
    "PasswordResetMiddleware",
    "Serializer",
    "ModelSerializer",
    "ListSerializer",
    "SerializerField",
    "ViewSet",
    "ModelViewSet",
    "ListModelMixin",
    "ViewSetRouter",
    "BrowsableApiMiddleware",
    "GraphQLMiddleware",
    "graphql_query",
    "graphql_mutation",
    "ChannelLayer",
    "WebSocketBroadcast",
    "WebSocketChannel",
    "Room",
    "Sitemap",
    "SitemapIndex",
    "RssFeed",
    "AtomFeed",
    "ContentTypeRegistry",
    "GenericForeignKey",
    "GenericRelation",
    "get_content_type",
    "get_object",
    "Point",
    "LineString",
    "Polygon",
    "MultiPoint",
    "MultiLineString",
    "MultiPolygon",
    "GeometryCollection",
    "GeographyColumn",
    "GeometryColumn",
    "SpatialQuery",
    "haversine_distance",
    "earth_distance",
    "to_geojson",
    "OpenTelemetryMiddleware",
    "configure_otel",
    "set_tracer",
    "get_tracer",
    "SentryMiddleware",
    "configure_sentry",
    "capture_exception",
    "set_user_context",
    "set_extra_context",
    "GrpcServer",
    "GrpcClient",
    "Http3Server",
    "Http3Client",
    # Additional protocols
    "WebTransportServer",
    "WebTransportClient",
    "WebTransportSession",
    "GrpcWebMiddleware",
    "GrpcWebServer",
    "SocketIOServer",
    "SocketIOSession",
    "SocketIOMiddleware",
    "MQTTBridge",
    "WebDAVMiddleware",
    "JSONRPCMiddleware",
    "XMLRPCMiddleware",
    "RawTCPServer",
    "UnixSocketServer",
    "UDPBroadcastServer",
    # WebSocket features
    "PresenceTracker",
    "HeartbeatManager",
    "WSAuthMiddleware",
    "require_ws_auth",
    "RateLimiter",
    "TypingIndicators",
    "RPCServer",
    "RPCClient",
    "rpc_method",
    "BinaryCodec",
    "MsgPackCodec",
    "JSONCodec",
    "register_codec",
    "ReconnectionHelper",
    "MultiServerBackend",
    "RedisPubSubBackend",
    "NATSBackend",
]

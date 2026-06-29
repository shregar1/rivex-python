"""Structured log message codes."""

from __future__ import annotations

# Application lifecycle
APP_STARTED = "app_started"
APP_SHUTDOWN = "app_shutdown"

# HTTP layer
REQUEST_STARTED = "request_started"
REQUEST_COMPLETED = "request_completed"
REQUEST_FAILED = "request_failed"
DOMAIN_ERROR = "domain_error"
UNHANDLED_ERROR = "unhandled_error"

# Controller invocation wrapper
CONTROLLER_STARTED = "controller_started"
CONTROLLER_COMPLETED = "controller_completed"
CONTROLLER_FAILED = "controller_failed"

# Service invocation wrapper
SERVICE_STARTED = "service_started"
SERVICE_COMPLETED = "service_completed"
SERVICE_FAILED = "service_failed"

# Persistence
DB_QUERY_SLOW = "db_query_slow"
REPOSITORY_STARTED = "repository_started"
REPOSITORY_COMPLETED = "repository_completed"
REPOSITORY_FAILED = "repository_failed"
REPOSITORY_OPERATION = "repository_operation"

# Utility invocation wrapper
UTILITY_STARTED = "utility_started"
UTILITY_COMPLETED = "utility_completed"
UTILITY_FAILED = "utility_failed"

# Outbound utilities
EMAIL_SENT = "email_sent"
EMAIL_SEND_FAILED = "email_send_failed"
EMAIL_NOT_CONFIGURED = "email_not_configured"
SMS_SENT = "sms_sent"
SMS_SEND_FAILED = "sms_send_failed"
SMS_NOT_CONFIGURED = "sms_not_configured"

# Items (example slice)
ITEM_CREATED = "item_created"
ITEM_FETCHED = "item_fetched"
ITEM_UPDATED = "item_updated"
ITEM_DELETED = "item_deleted"
ITEMS_LISTED = "items_listed"

DEFAULT_REDACT_FIELDS: tuple[str, ...] = (
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "secret",
    "jwt_secret",
    "api_key",
)

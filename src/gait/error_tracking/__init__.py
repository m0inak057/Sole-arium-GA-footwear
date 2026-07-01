"""Error tracking module (Sentry integration)."""
from gait.error_tracking.sentry_config import (
    SentryConfig,
    add_sentry_breadcrumb,
    capture_sentry_exception,
    capture_sentry_message,
    init_sentry,
    set_sentry_context,
)

__all__ = [
    "SentryConfig",
    "init_sentry",
    "set_sentry_context",
    "add_sentry_breadcrumb",
    "capture_sentry_exception",
    "capture_sentry_message",
]


"""Error tracking module (Sentry integration)."""

MODULE_STATUS = "UNUSED"
# init_sentry() is never called at startup — gait.api.main has no Sentry
# wiring despite Settings.sentry_dsn existing in gait.config.settings (itself
# also unused). Kept as scaffolding for production error tracking. To
# activate: call init_sentry(dsn=os.getenv("SENTRY_DSN")) from main.py's
# startup event, alongside the existing MinIO/rate-limit init calls.

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


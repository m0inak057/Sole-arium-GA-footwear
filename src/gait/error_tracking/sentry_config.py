"""Sentry error tracking configuration."""
from __future__ import annotations

from typing import Optional

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from src.gait.common.logging_utils import get_logger

logger = get_logger(__name__)


class SentryConfig:
    """Sentry configuration."""

    def __init__(
        self,
        dsn: Optional[str] = None,
        environment: str = "production",
        release: Optional[str] = None,
        trace_sample_rate: float = 0.1,
        profiles_sample_rate: float = 0.1,
        before_send=None,
    ):
        """Initialize Sentry config.

        Args:
            dsn: Sentry DSN (if None, Sentry is disabled)
            environment: Environment name (production, staging, development)
            release: Release version
            trace_sample_rate: Tracing sample rate (0.0-1.0)
            profiles_sample_rate: Profiling sample rate (0.0-1.0)
            before_send: Custom before_send hook for filtering events
        """
        self.dsn = dsn
        self.environment = environment
        self.release = release
        self.trace_sample_rate = trace_sample_rate
        self.profiles_sample_rate = profiles_sample_rate
        self.before_send = before_send


def init_sentry(config: SentryConfig) -> bool:
    """Initialize Sentry error tracking.

    Args:
        config: Sentry configuration

    Returns:
        True if Sentry initialized, False if disabled or error
    """
    if not config.dsn:
        logger.info("sentry.disabled")
        return False

    try:
        sentry_sdk.init(
            dsn=config.dsn,
            environment=config.environment,
            release=config.release,
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
            ],
            traces_sample_rate=config.trace_sample_rate,
            profiles_sample_rate=config.profiles_sample_rate,
            before_send=config.before_send,
            attach_stacktrace=True,
        )
        logger.info(
            "sentry.initialized",
            extra={
                "environment": config.environment,
                "release": config.release,
            },
        )
        return True

    except Exception as e:
        logger.error("sentry.init_failed", extra={"error": str(e)})
        return False


def set_sentry_context(user_id: Optional[str] = None, **extra_context) -> None:
    """Set Sentry context for current transaction.

    Args:
        user_id: User ID for context
        **extra_context: Additional context data
    """
    if user_id:
        sentry_sdk.set_user({"id": user_id})

    if extra_context:
        sentry_sdk.set_context("custom", extra_context)


def add_sentry_breadcrumb(
    message: str,
    category: str = "info",
    level: str = "info",
    data: Optional[dict] = None,
) -> None:
    """Add breadcrumb to Sentry transaction.

    Args:
        message: Breadcrumb message
        category: Breadcrumb category
        level: Breadcrumb level (debug, info, warning, error)
        data: Additional data for breadcrumb
    """
    try:
        from sentry_sdk import get_client
        client = get_client()
        if client.is_active():
            client.capture_breadcrumb(
                message=message,
                category=category,
                level=level,
                data=data or {},
            )
    except Exception as e:
        logger.debug("sentry.breadcrumb_failed", extra={"error": str(e)})


def capture_sentry_exception(
    exception: Exception,
    level: str = "error",
    tags: Optional[dict] = None,
) -> str:
    """Capture exception in Sentry.

    Args:
        exception: Exception to capture
        level: Event level (error, warning, info, debug)
        tags: Event tags

    Returns:
        Event ID in Sentry
    """
    return sentry_sdk.capture_exception(
        exception,
        level=level,
        tags=tags or {},
    )


def capture_sentry_message(
    message: str,
    level: str = "info",
    tags: Optional[dict] = None,
) -> str:
    """Capture message in Sentry.

    Args:
        message: Message to capture
        level: Message level
        tags: Event tags

    Returns:
        Event ID in Sentry
    """
    return sentry_sdk.capture_message(
        message,
        level=level,
        tags=tags or {},
    )

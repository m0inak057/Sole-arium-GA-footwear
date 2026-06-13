"""Unit tests for error tracking (Sentry)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.gait.error_tracking.sentry_config import (
    SentryConfig,
    add_sentry_breadcrumb,
    capture_sentry_exception,
    capture_sentry_message,
    init_sentry,
    set_sentry_context,
)


class TestSentryConfig:
    """Tests for SentryConfig."""

    def test_create_config_defaults(self):
        """Test creating config with defaults."""
        config = SentryConfig()
        assert config.dsn is None
        assert config.environment == "production"
        assert config.release is None
        assert config.trace_sample_rate == 0.1
        assert config.profiles_sample_rate == 0.1

    def test_create_config_custom(self):
        """Test creating config with custom values."""
        config = SentryConfig(
            dsn="https://key@sentry.io/12345",
            environment="staging",
            release="1.0.0",
            trace_sample_rate=0.5,
            profiles_sample_rate=0.2,
        )
        assert config.dsn == "https://key@sentry.io/12345"
        assert config.environment == "staging"
        assert config.release == "1.0.0"
        assert config.trace_sample_rate == 0.5
        assert config.profiles_sample_rate == 0.2

    def test_config_with_before_send(self):
        """Test config with before_send hook."""
        def before_send(event, hint):
            return event

        config = SentryConfig(before_send=before_send)
        assert config.before_send is not None
        assert config.before_send({"test": "event"}, {}) == {"test": "event"}


class TestInitSentry:
    """Tests for Sentry initialization."""

    def test_init_sentry_disabled(self):
        """Test that Sentry is disabled when DSN is None."""
        config = SentryConfig(dsn=None)
        result = init_sentry(config)
        assert result is False

    def test_init_sentry_enabled(self):
        """Test Sentry initialization with DSN."""
        with patch("sentry_sdk.init") as mock_init:
            config = SentryConfig(
                dsn="https://key@sentry.io/12345",
                environment="production",
            )
            result = init_sentry(config)
            assert result is True
            mock_init.assert_called_once()

    def test_init_sentry_with_release(self):
        """Test Sentry initialization with release."""
        with patch("sentry_sdk.init") as mock_init:
            config = SentryConfig(
                dsn="https://key@sentry.io/12345",
                release="1.0.0",
            )
            init_sentry(config)
            args, kwargs = mock_init.call_args
            assert kwargs["release"] == "1.0.0"

    def test_init_sentry_error(self):
        """Test handling of Sentry initialization error."""
        with patch("sentry_sdk.init", side_effect=Exception("Init failed")):
            config = SentryConfig(dsn="https://key@sentry.io/12345")
            result = init_sentry(config)
            assert result is False


class TestSetSentryContext:
    """Tests for setting Sentry context."""

    def test_set_sentry_context_user(self):
        """Test setting user context."""
        with patch("sentry_sdk.set_user") as mock_set_user:
            set_sentry_context(user_id="user123")
            mock_set_user.assert_called_once_with({"id": "user123"})

    def test_set_sentry_context_custom(self):
        """Test setting custom context."""
        with patch("sentry_sdk.set_context") as mock_set_context:
            set_sentry_context(session_id="sess456", ip="192.168.1.1")
            mock_set_context.assert_called_once()
            args = mock_set_context.call_args[0]
            assert args[0] == "custom"

    def test_set_sentry_context_both(self):
        """Test setting both user and custom context."""
        with patch("sentry_sdk.set_user") as mock_user:
            with patch("sentry_sdk.set_context") as mock_context:
                set_sentry_context(user_id="user789", request_id="req123")
                mock_user.assert_called_once()
                mock_context.assert_called_once()


class TestAddSentryBreadcrumb:
    """Tests for adding Sentry breadcrumb."""

    def test_add_breadcrumb_no_error(self):
        """Test adding breadcrumb (function succeeds without errors)."""
        # Breadcrumb functions handle errors gracefully
        add_sentry_breadcrumb("User logged in")
        add_sentry_breadcrumb(
            "Database query executed",
            category="database",
            level="debug",
        )
        add_sentry_breadcrumb(
            "File uploaded",
            data={"size": 1024, "type": "video"},
        )


class TestCaptureSentryException:
    """Tests for capturing Sentry exceptions."""

    def test_capture_exception(self):
        """Test capturing exception."""
        with patch("sentry_sdk.capture_exception") as mock_capture:
            mock_capture.return_value = "event-id-123"
            error = ValueError("Test error")
            result = capture_sentry_exception(error)
            assert result == "event-id-123"
            mock_capture.assert_called_once()

    def test_capture_exception_with_level(self):
        """Test capturing exception with custom level."""
        with patch("sentry_sdk.capture_exception") as mock_capture:
            error = Exception("Warning error")
            capture_sentry_exception(error, level="warning")
            args, kwargs = mock_capture.call_args
            assert kwargs["level"] == "warning"

    def test_capture_exception_with_tags(self):
        """Test capturing exception with tags."""
        with patch("sentry_sdk.capture_exception") as mock_capture:
            error = RuntimeError("Runtime error")
            capture_sentry_exception(
                error,
                tags={"endpoint": "/api/sessions", "method": "POST"},
            )
            args, kwargs = mock_capture.call_args
            assert kwargs["tags"]["endpoint"] == "/api/sessions"


class TestCaptureSentryMessage:
    """Tests for capturing Sentry messages."""

    def test_capture_message(self):
        """Test capturing message."""
        with patch("sentry_sdk.capture_message") as mock_capture:
            mock_capture.return_value = "event-id-456"
            result = capture_sentry_message("Something happened")
            assert result == "event-id-456"
            mock_capture.assert_called_once()

    def test_capture_message_with_level(self):
        """Test capturing message with level."""
        with patch("sentry_sdk.capture_message") as mock_capture:
            capture_sentry_message("Warning message", level="warning")
            args, kwargs = mock_capture.call_args
            assert kwargs["level"] == "warning"

    def test_capture_message_with_tags(self):
        """Test capturing message with tags."""
        with patch("sentry_sdk.capture_message") as mock_capture:
            capture_sentry_message(
                "System info",
                tags={"service": "gait-analysis", "version": "1.0.0"},
            )
            args, kwargs = mock_capture.call_args
            assert kwargs["tags"]["service"] == "gait-analysis"

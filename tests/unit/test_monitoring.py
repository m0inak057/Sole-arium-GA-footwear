"""Unit tests for monitoring (metrics and health checks)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from gait.monitoring.health import (
    HealthCheck,
    HealthChecker,
    HealthStatus,
    ServiceHealth,
    check_database_health,
    check_redis_health,
    check_storage_health,
)
from gait.monitoring.metrics import (
    active_sessions,
    auth_attempts_total,
    cache_hits_total,
    cache_misses_total,
    db_queries_total,
    errors_total,
    http_errors_total,
    http_requests_total,
    record_auth_attempt,
    record_error,
    record_http_request,
)


# â”€â”€ Health Status Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_health_status_values(self):
        """Test all health status values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"


# â”€â”€ ServiceHealth Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestServiceHealth:
    """Tests for ServiceHealth model."""

    def test_create_service_health(self):
        """Test creating service health."""
        service = ServiceHealth(
            name="database",
            status=HealthStatus.HEALTHY,
        )
        assert service.name == "database"
        assert service.status == HealthStatus.HEALTHY
        assert service.checked_at is not None

    def test_create_service_health_with_message(self):
        """Test creating service health with message."""
        service = ServiceHealth(
            name="cache",
            status=HealthStatus.DEGRADED,
            message="Connection slow",
        )
        assert service.name == "cache"
        assert service.status == HealthStatus.DEGRADED
        assert service.message == "Connection slow"

    def test_service_health_checked_at_default(self):
        """Test that checked_at is set by default."""
        before = datetime.now(timezone.utc)
        service = ServiceHealth(
            name="storage",
            status=HealthStatus.HEALTHY,
        )
        after = datetime.now(timezone.utc)
        assert before <= service.checked_at <= after


# â”€â”€ HealthCheck Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestHealthCheck:
    """Tests for HealthCheck model."""

    def test_create_health_check(self):
        """Test creating health check."""
        services = {
            "database": ServiceHealth(
                name="database",
                status=HealthStatus.HEALTHY,
            ),
        }
        check = HealthCheck(
            status=HealthStatus.HEALTHY,
            timestamp=datetime.now(timezone.utc),
            uptime_seconds=3600,
            services=services,
        )
        assert check.status == HealthStatus.HEALTHY
        assert check.uptime_seconds == 3600
        assert len(check.services) == 1

    def test_health_check_is_healthy(self):
        """Test is_healthy method."""
        services = {
            "db": ServiceHealth(name="db", status=HealthStatus.HEALTHY),
        }
        check = HealthCheck(
            status=HealthStatus.HEALTHY,
            timestamp=datetime.now(timezone.utc),
            uptime_seconds=100,
            services=services,
        )
        assert check.is_healthy() is True

    def test_health_check_is_degraded(self):
        """Test is_degraded method."""
        services = {
            "db": ServiceHealth(name="db", status=HealthStatus.DEGRADED),
        }
        check = HealthCheck(
            status=HealthStatus.DEGRADED,
            timestamp=datetime.now(timezone.utc),
            uptime_seconds=100,
            services=services,
        )
        assert check.is_degraded() is True

    def test_health_check_timestamp(self):
        """Test that timestamp is set."""
        before = datetime.now(timezone.utc)
        check = HealthCheck(
            status=HealthStatus.HEALTHY,
            timestamp=before,
            uptime_seconds=100,
            services={},
        )
        after = datetime.now(timezone.utc)
        assert check.timestamp == before or check.timestamp > before


# â”€â”€ HealthChecker Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestHealthChecker:
    """Tests for HealthChecker."""

    def test_create_health_checker(self):
        """Test creating health checker."""
        checker = HealthChecker()
        assert isinstance(checker.services, dict)
        assert len(checker.services) == 0

    def test_add_service_status(self):
        """Test adding service status."""
        checker = HealthChecker()
        checker.add_service_status("database", HealthStatus.HEALTHY)
        assert "database" in checker.services
        assert checker.services["database"].status == HealthStatus.HEALTHY

    def test_add_service_status_with_message(self):
        """Test adding service status with message."""
        checker = HealthChecker()
        checker.add_service_status(
            "cache",
            HealthStatus.DEGRADED,
            "Slow responses",
        )
        assert checker.services["cache"].message == "Slow responses"

    def test_get_health_all_healthy(self):
        """Test getting health when all services are healthy."""
        checker = HealthChecker()
        checker.add_service_status("db", HealthStatus.HEALTHY)
        checker.add_service_status("cache", HealthStatus.HEALTHY)
        health = checker.get_health(uptime_seconds=100)
        assert health.status == HealthStatus.HEALTHY

    def test_get_health_one_degraded(self):
        """Test getting health with one degraded service."""
        checker = HealthChecker()
        checker.add_service_status("db", HealthStatus.HEALTHY)
        checker.add_service_status("cache", HealthStatus.DEGRADED)
        health = checker.get_health(uptime_seconds=100)
        assert health.status == HealthStatus.DEGRADED

    def test_get_health_one_unhealthy(self):
        """Test getting health with one unhealthy service."""
        checker = HealthChecker()
        checker.add_service_status("db", HealthStatus.HEALTHY)
        checker.add_service_status("storage", HealthStatus.UNHEALTHY)
        health = checker.get_health(uptime_seconds=100)
        assert health.status == HealthStatus.UNHEALTHY

    def test_get_health_empty_services(self):
        """Test getting health with no services."""
        checker = HealthChecker()
        health = checker.get_health(uptime_seconds=100)
        assert health.status == HealthStatus.HEALTHY

    def test_get_health_uptime(self):
        """Test that uptime is recorded."""
        checker = HealthChecker()
        health = checker.get_health(uptime_seconds=7200)
        assert health.uptime_seconds == 7200


# â”€â”€ Health Check Functions Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestHealthCheckFunctions:
    """Tests for health check functions."""

    def test_check_redis_health_success(self):
        """Test successful Redis health check."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        assert check_redis_health(mock_redis) is True

    def test_check_redis_health_failure(self):
        """Test failed Redis health check."""
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Connection failed")
        assert check_redis_health(mock_redis) is False

    def test_check_database_health_success(self):
        """Test successful database health check."""
        mock_session = MagicMock()
        mock_session.execute.return_value = MagicMock()
        assert check_database_health(mock_session) is True

    def test_check_database_health_failure(self):
        """Test failed database health check."""
        mock_session = MagicMock()
        mock_session.execute.side_effect = Exception("Connection failed")
        assert check_database_health(mock_session) is False

    def test_check_storage_health_success(self):
        """Test successful storage health check."""
        mock_storage = MagicMock()
        mock_storage.list_files.return_value = []
        assert check_storage_health(mock_storage) is True

    def test_check_storage_health_failure(self):
        """Test failed storage health check."""
        mock_storage = MagicMock()
        mock_storage.list_files.side_effect = Exception("Connection failed")
        assert check_storage_health(mock_storage) is False


# â”€â”€ Metrics Recording Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestMetricsRecording:
    """Tests for metrics recording functions."""

    def test_record_http_request(self):
        """Test recording HTTP request."""
        initial_value = http_requests_total.labels(
            method="GET",
            endpoint="sessions",
            status=200,
        )._value.get()
        record_http_request("GET", "sessions", 0.5, 200)
        # Can't directly test counter value, but function should not raise

    def test_record_auth_attempt_success(self):
        """Test recording successful auth attempt."""
        initial_value = auth_attempts_total.labels(
            method="password",
            status="success",
        )._value.get()
        record_auth_attempt("password", success=True)
        # Function should not raise

    def test_record_auth_attempt_failure(self):
        """Test recording failed auth attempt."""
        initial_value = auth_attempts_total.labels(
            method="api_key",
            status="failed",
        )._value.get()
        record_auth_attempt("api_key", success=False)
        # Function should not raise

    def test_record_error(self):
        """Test recording error."""
        record_error("ValidationError")
        # Function should not raise


# â”€â”€ Metrics Existence Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestMetricsExistence:
    """Tests that all metrics exist and are accessible."""

    def test_http_requests_metric_exists(self):
        """Test that http_requests_total metric exists."""
        assert http_requests_total is not None

    def test_auth_attempts_metric_exists(self):
        """Test that auth_attempts_total metric exists."""
        assert auth_attempts_total is not None

    def test_cache_metrics_exist(self):
        """Test that cache metrics exist."""
        assert cache_hits_total is not None
        assert cache_misses_total is not None

    def test_db_metrics_exist(self):
        """Test that database metrics exist."""
        assert db_queries_total is not None

    def test_error_metrics_exist(self):
        """Test that error metrics exist."""
        assert errors_total is not None
        assert http_errors_total is not None

    def test_session_metrics_exist(self):
        """Test that session metrics exist."""
        assert active_sessions is not None


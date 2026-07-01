"""Health check utilities for monitoring."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel

from gait.common.logging_utils import get_logger

logger = get_logger(__name__)


class HealthStatus(str, Enum):
    """Health status values."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ServiceHealth(BaseModel):
    """Health status for a service component."""
    name: str
    status: HealthStatus
    message: Optional[str] = None
    checked_at: datetime = None

    def __init__(self, **data):
        """Initialize service health."""
        if "checked_at" not in data:
            data["checked_at"] = datetime.now(timezone.utc)
        super().__init__(**data)


class HealthCheck(BaseModel):
    """Overall health check result."""
    status: HealthStatus
    timestamp: datetime
    uptime_seconds: int
    services: Dict[str, ServiceHealth]

    def is_healthy(self) -> bool:
        """Check if system is healthy.

        Returns:
            True if all services are healthy
        """
        return self.status == HealthStatus.HEALTHY

    def is_degraded(self) -> bool:
        """Check if system is degraded.

        Returns:
            True if some services are degraded or unhealthy
        """
        return self.status in (HealthStatus.DEGRADED, HealthStatus.UNHEALTHY)


class HealthChecker:
    """Aggregates health checks for all services."""

    def __init__(self):
        """Initialize health checker."""
        self.services: Dict[str, ServiceHealth] = {}
        self.start_time = datetime.now(timezone.utc)

    def register_check(self, name: str, checker_func) -> None:
        """Register a health check function.

        Args:
            name: Service name
            checker_func: Async callable that returns (bool, str) for (is_healthy, message)
        """
        self.services[name] = None

    def add_service_status(
        self,
        name: str,
        status: HealthStatus,
        message: Optional[str] = None,
    ) -> None:
        """Add service health status.

        Args:
            name: Service name
            status: Health status
            message: Optional status message
        """
        self.services[name] = ServiceHealth(
            name=name,
            status=status,
            message=message,
        )
        logger.info(
            "health.service_status",
            extra={"service": name, "status": status},
        )

    def get_health(self, uptime_seconds: int = 0) -> HealthCheck:
        """Get overall health status.

        Args:
            uptime_seconds: Application uptime in seconds

        Returns:
            HealthCheck with overall and per-service status
        """
        # Determine overall status
        statuses = [s.status for s in self.services.values() if s]
        if not statuses:
            overall_status = HealthStatus.HEALTHY
        elif HealthStatus.UNHEALTHY in statuses:
            overall_status = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return HealthCheck(
            status=overall_status,
            timestamp=datetime.now(timezone.utc),
            uptime_seconds=uptime_seconds,
            services=self.services,
        )


def check_redis_health(redis_client) -> bool:
    """Check Redis health.

    Args:
        redis_client: Redis client instance

    Returns:
        True if Redis is healthy
    """
    try:
        redis_client.ping()
        return True
    except Exception as e:
        logger.error("health.redis_check_failed", extra={"error": str(e)})
        return False


def check_database_health(db_session) -> bool:
    """Check database health.

    Args:
        db_session: SQLAlchemy database session

    Returns:
        True if database is healthy
    """
    try:
        from sqlalchemy import text
        db_session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("health.db_check_failed", extra={"error": str(e)})
        return False


def check_storage_health(storage) -> bool:
    """Check storage health.

    Args:
        storage: Storage backend instance

    Returns:
        True if storage is healthy
    """
    try:
        # Try to list files (no-op that checks connectivity)
        storage.list_files(prefix="", max_keys=1)
        return True
    except Exception as e:
        logger.error("health.storage_check_failed", extra={"error": str(e)})
        return False


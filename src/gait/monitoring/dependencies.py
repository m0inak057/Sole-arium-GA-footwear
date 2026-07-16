"""Monitoring dependencies for FastAPI."""
from __future__ import annotations

MODULE_STATUS = "UNUSED"
# Part of the gait.monitoring package — see gait/monitoring/__init__.py for
# why this exists and what activating it would take.

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

from gait.common.logging_utils import get_logger

logger = get_logger(__name__)


def get_metrics_endpoint() -> tuple[bytes, str]:
    """Get Prometheus metrics in text format.

    Returns:
        Tuple of (metrics_bytes, content_type)
    """
    try:
        # Use default registry
        metrics = generate_latest()
        logger.debug("metrics.generated", extra={"size_bytes": len(metrics)})
        return metrics, CONTENT_TYPE_LATEST
    except Exception as e:
        logger.error("metrics.generation_failed", extra={"error": str(e)})
        return b"", CONTENT_TYPE_LATEST


def get_health_check_result(health_checker) -> dict:
    """Get health check result as dict.

    Args:
        health_checker: HealthChecker instance

    Returns:
        Health check result as dict
    """
    try:
        health = health_checker.get_health()
        result = {
            "status": health.status.value,
            "timestamp": health.timestamp.isoformat(),
            "uptime_seconds": health.uptime_seconds,
            "services": {
                name: {
                    "status": service.status.value,
                    "message": service.message,
                    "checked_at": service.checked_at.isoformat() if service.checked_at else None,
                }
                for name, service in health.services.items()
            },
        }
        logger.debug("health.check_complete", extra={"status": health.status.value})
        return result
    except Exception as e:
        logger.error("health.check_failed", extra={"error": str(e)})
        return {
            "status": "unhealthy",
            "error": str(e),
        }


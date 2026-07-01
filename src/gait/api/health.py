"""Health check endpoint for API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from gait.monitoring import HealthChecker, HealthStatus

router = APIRouter(prefix="/health", tags=["health"])
health_checker: HealthChecker = None


def set_health_checker(checker: HealthChecker) -> None:
    """Set the health checker instance for endpoints.

    Args:
        checker: HealthChecker instance
    """
    global health_checker
    health_checker = checker


@router.get("/", response_model=dict)
async def health_check():
    """Get application health status.

    Returns:
        Health check result with status of all services
    """
    if not health_checker:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Health checker not initialized",
        )

    health = health_checker.get_health()

    status_code = (
        status.HTTP_200_OK
        if health.status == HealthStatus.HEALTHY
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    return {
        "status": health.status.value,
        "timestamp": health.timestamp.isoformat(),
        "uptime_seconds": health.uptime_seconds,
        "services": {
            name: {
                "status": service.status.value,
                "message": service.message,
            }
            for name, service in health.services.items()
        },
    }


@router.get("/ready", response_model=dict)
async def ready_check():
    """Check if application is ready to serve requests.

    Returns:
        Ready status
    """
    if not health_checker:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Health checker not initialized",
        )

    health = health_checker.get_health()
    is_ready = health.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)

    status_code = (
        status.HTTP_200_OK
        if is_ready
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    return {
        "ready": is_ready,
        "status": health.status.value,
    }


@router.get("/live", response_model=dict)
async def live_check():
    """Check if application is alive.

    Returns:
        Alive status
    """
    return {"alive": True}


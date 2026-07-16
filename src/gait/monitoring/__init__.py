"""Monitoring module (Prometheus metrics and health checks)."""

MODULE_STATUS = "UNUSED"
# Not wired into the live API: MetricsMiddleware is never passed to
# app.add_middleware() in gait.api.main, and no endpoint calls
# get_metrics_endpoint() or get_health_check_result() (main.py's own /health
# is a hand-rolled liveness probe, unrelated to this HealthChecker). Kept as
# scaffolding for Prometheus/health-check integration. To activate: add
# app.add_middleware(MetricsMiddleware) and a GET /metrics route in
# gait.api.main that returns get_metrics_endpoint()'s output.

from gait.monitoring.dependencies import get_health_check_result, get_metrics_endpoint
from gait.monitoring.health import (
    HealthCheck,
    HealthChecker,
    HealthStatus,
    ServiceHealth,
    check_database_health,
    check_redis_health,
    check_storage_health,
)
from gait.monitoring.middleware import MetricsMiddleware
from gait.monitoring.metrics import (
    active_sessions,
    app_info,
    auth_attempts_total,
    cache_hits_total,
    cache_misses_total,
    cache_operations_duration_seconds,
    db_active_connections,
    db_connection_pool_size,
    db_queries_total,
    db_query_duration_seconds,
    errors_total,
    http_errors_total,
    http_request_duration_seconds,
    http_request_size_bytes,
    http_requests_total,
    http_response_size_bytes,
    rate_limit_exceeded_total,
    record_auth_attempt,
    record_cache_operation,
    record_error,
    record_http_request,
    record_storage_operation,
    session_processing_duration_seconds,
    session_queue_size,
    session_uploads_total,
    storage_bytes_transferred,
    storage_operation_duration_seconds,
    storage_operations_total,
)

__all__ = [
    "MetricsMiddleware",
    "HealthChecker",
    "HealthCheck",
    "ServiceHealth",
    "HealthStatus",
    "check_redis_health",
    "check_database_health",
    "check_storage_health",
    "get_metrics_endpoint",
    "get_health_check_result",
    "record_http_request",
    "record_cache_operation",
    "record_storage_operation",
    "record_auth_attempt",
    "record_error",
    "http_requests_total",
    "http_request_duration_seconds",
    "http_request_size_bytes",
    "http_response_size_bytes",
    "active_sessions",
    "session_uploads_total",
    "session_processing_duration_seconds",
    "session_queue_size",
    "auth_attempts_total",
    "cache_hits_total",
    "cache_misses_total",
    "cache_operations_duration_seconds",
    "db_queries_total",
    "db_query_duration_seconds",
    "db_connection_pool_size",
    "db_active_connections",
    "storage_operations_total",
    "storage_bytes_transferred",
    "storage_operation_duration_seconds",
    "errors_total",
    "http_errors_total",
    "app_info",
    "rate_limit_exceeded_total",
]


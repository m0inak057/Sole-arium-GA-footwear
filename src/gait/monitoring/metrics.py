"""Prometheus metrics for application monitoring."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Summary

from gait.common.logging_utils import get_logger

logger = get_logger(__name__)


# â”€â”€ Request Metrics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


http_requests_total = Counter(
    "gait_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "gait_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0),
)

http_request_size_bytes = Summary(
    "gait_http_request_size_bytes",
    "HTTP request body size in bytes",
    ["method", "endpoint"],
)

http_response_size_bytes = Summary(
    "gait_http_response_size_bytes",
    "HTTP response body size in bytes",
    ["method", "endpoint"],
)


# â”€â”€ Session Metrics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


active_sessions = Gauge(
    "gait_active_sessions",
    "Number of active sessions",
)

session_uploads_total = Counter(
    "gait_session_uploads_total",
    "Total files uploaded",
    ["status"],  # success, failed
)

session_processing_duration_seconds = Histogram(
    "gait_session_processing_duration_seconds",
    "Session processing duration in seconds",
    ["stage"],  # decode, sync, calibrate, segment, track, roi
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0),
)

session_queue_size = Gauge(
    "gait_session_queue_size",
    "Number of sessions in processing queue",
)


# â”€â”€ Authentication Metrics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


auth_attempts_total = Counter(
    "gait_auth_attempts_total",
    "Total authentication attempts",
    ["method", "status"],  # method: password, api_key; status: success, failed
)

auth_tokens_issued_total = Counter(
    "gait_auth_tokens_issued_total",
    "Total tokens issued",
    ["token_type"],  # access, refresh
)

rate_limit_exceeded_total = Counter(
    "gait_rate_limit_exceeded_total",
    "Total rate limit exceeded events",
    ["identifier_type"],  # user, api_key, ip
)


# â”€â”€ Cache Metrics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


cache_hits_total = Counter(
    "gait_cache_hits_total",
    "Total cache hits",
    ["cache_key"],
)

cache_misses_total = Counter(
    "gait_cache_misses_total",
    "Total cache misses",
    ["cache_key"],
)

cache_operations_duration_seconds = Histogram(
    "gait_cache_operations_duration_seconds",
    "Cache operation duration in seconds",
    ["operation"],  # get, set, delete
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1),
)

cache_size_bytes = Gauge(
    "gait_cache_size_bytes",
    "Total cache size in bytes",
)


# â”€â”€ Database Metrics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


db_queries_total = Counter(
    "gait_db_queries_total",
    "Total database queries",
    ["operation"],  # select, insert, update, delete
)

db_query_duration_seconds = Histogram(
    "gait_db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5),
)

db_connection_pool_size = Gauge(
    "gait_db_connection_pool_size",
    "Database connection pool size",
)

db_active_connections = Gauge(
    "gait_db_active_connections",
    "Number of active database connections",
)


# â”€â”€ Storage Metrics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


storage_operations_total = Counter(
    "gait_storage_operations_total",
    "Total storage operations",
    ["operation", "backend", "status"],  # operation: upload, download, delete; backend: s3, minio; status: success, failed
)

storage_bytes_transferred = Counter(
    "gait_storage_bytes_transferred",
    "Total bytes transferred to/from storage",
    ["operation", "backend"],  # operation: upload, download
)

storage_operation_duration_seconds = Histogram(
    "gait_storage_operation_duration_seconds",
    "Storage operation duration in seconds",
    ["operation", "backend"],
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0),
)


# â”€â”€ Error Metrics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


errors_total = Counter(
    "gait_errors_total",
    "Total errors by type",
    ["error_type"],  # ValidationError, AuthenticationError, ProcessingError, StorageError
)

http_errors_total = Counter(
    "gait_http_errors_total",
    "Total HTTP errors by status code",
    ["status_code"],
)


# â”€â”€ System Metrics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


app_info = Gauge(
    "gait_app_info",
    "Application info",
    ["version", "environment"],
)

uptime_seconds = Gauge(
    "gait_uptime_seconds",
    "Application uptime in seconds",
)

workers_active = Gauge(
    "gait_workers_active",
    "Number of active background workers",
)


def record_http_request(method: str, endpoint: str, duration_seconds: float, status: int):
    """Record HTTP request metrics.

    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint path
        duration_seconds: Request duration
        status: HTTP status code
    """
    http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
    http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration_seconds)


def record_cache_operation(operation: str, duration_seconds: float, key: str = ""):
    """Record cache operation metrics.

    Args:
        operation: Operation type (get, set, delete)
        duration_seconds: Operation duration
        key: Cache key (optional)
    """
    cache_operations_duration_seconds.labels(operation=operation).observe(duration_seconds)
    if operation == "get":
        cache_hits_total.labels(cache_key=key or "unknown").inc()


def record_storage_operation(
    operation: str,
    backend: str,
    duration_seconds: float,
    bytes_transferred: int = 0,
    status: str = "success",
):
    """Record storage operation metrics.

    Args:
        operation: Operation type (upload, download, delete)
        backend: Backend type (s3, minio)
        duration_seconds: Operation duration
        bytes_transferred: Bytes transferred
        status: Operation status (success, failed)
    """
    storage_operations_total.labels(
        operation=operation,
        backend=backend,
        status=status,
    ).inc()
    if bytes_transferred > 0:
        storage_bytes_transferred.labels(
            operation=operation,
            backend=backend,
        ).inc(bytes_transferred)
    storage_operation_duration_seconds.labels(
        operation=operation,
        backend=backend,
    ).observe(duration_seconds)


def record_auth_attempt(method: str, success: bool):
    """Record authentication attempt metrics.

    Args:
        method: Authentication method (password, api_key)
        success: Whether authentication succeeded
    """
    status = "success" if success else "failed"
    auth_attempts_total.labels(method=method, status=status).inc()


def record_error(error_type: str):
    """Record error metrics.

    Args:
        error_type: Type of error
    """
    errors_total.labels(error_type=error_type).inc()


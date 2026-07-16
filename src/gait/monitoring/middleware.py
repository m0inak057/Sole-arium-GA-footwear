"""Middleware for instrumenting HTTP requests with metrics."""
from __future__ import annotations

MODULE_STATUS = "UNUSED"
# Part of the gait.monitoring package — see gait/monitoring/__init__.py for
# why this exists and what activating it would take.

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from gait.common.logging_utils import get_logger
from gait.monitoring.metrics import (
    http_errors_total,
    http_request_duration_seconds,
    http_request_size_bytes,
    http_requests_total,
    http_response_size_bytes,
)

logger = get_logger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware for collecting HTTP metrics."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and collect metrics.

        Args:
            request: HTTP request
            call_next: Next middleware/handler

        Returns:
            HTTP response with metrics recorded
        """
        start_time = time.time()
        method = request.method
        path = request.url.path

        # Extract endpoint (first path segment)
        endpoint = path.split("/")[1] if path else "root"

        try:
            # Get request size
            request_body = await request.body()
            request_size = len(request_body)

            # Process request
            response = await call_next(request)

            # Get response size
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk

            response_size = len(response_body)

            # Record metrics
            duration = time.time() - start_time
            status = response.status_code

            http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status=status,
            ).inc()

            http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint,
            ).observe(duration)

            if request_size > 0:
                http_request_size_bytes.labels(
                    method=method,
                    endpoint=endpoint,
                ).observe(request_size)

            if response_size > 0:
                http_response_size_bytes.labels(
                    method=method,
                    endpoint=endpoint,
                ).observe(response_size)

            # Record HTTP errors
            if status >= 400:
                http_errors_total.labels(status_code=status).inc()
                logger.warning(
                    "http.error",
                    extra={
                        "method": method,
                        "path": path,
                        "status": status,
                        "duration_ms": int(duration * 1000),
                    },
                )
            else:
                logger.info(
                    "http.request",
                    extra={
                        "method": method,
                        "path": path,
                        "status": status,
                        "duration_ms": int(duration * 1000),
                    },
                )

            # Return response with new body
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                "http.exception",
                extra={
                    "method": method,
                    "path": path,
                    "error": str(e),
                    "duration_ms": int(duration * 1000),
                },
            )
            http_errors_total.labels(status_code=500).inc()
            raise


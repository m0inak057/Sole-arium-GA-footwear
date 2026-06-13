"""Prometheus metrics endpoint for API."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/", response_class=Response)
async def metrics():
    """Get Prometheus metrics in text format.

    Returns:
        Prometheus metrics in text/plain format
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )

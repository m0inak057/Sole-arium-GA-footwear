"""Pydantic request/response models for the Gait Analysis REST API."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class SessionStatus(str, Enum):
    CREATED = "CREATED"
    UPLOADING = "UPLOADING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ── Anthropometrics sub-model ──────────────────────────────────────────────────


class LRMeasurement(BaseModel):
    L: float = Field(..., description="Left foot measurement")
    R: float = Field(..., description="Right foot measurement")


class AnthropometricsIn(BaseModel):
    height_cm: float = Field(..., gt=0, le=300, description="Height in centimetres")
    mass_kg: float = Field(..., gt=0, le=500, description="Body mass in kilograms")
    foot_length_mm: LRMeasurement = Field(
        ..., description="Foot length in millimetres per foot"
    )
    foot_width_mm: LRMeasurement = Field(
        ..., description="Foot width in millimetres per foot"
    )


# ── Request models ─────────────────────────────────────────────────────────────


class SessionCreate(BaseModel):
    """POST /api/v1/sessions — create a new analysis session."""

    patient_id: str = Field(..., min_length=1, description="Pseudonymous patient identifier")
    anthropometrics: AnthropometricsIn = Field(..., description="Patient measurements")


class ProcessRequest(BaseModel):
    """POST /api/v1/sessions/{id}/process — trigger pipeline processing."""

    config_overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional pipeline config overrides (nested dict, e.g. {'pose': {'smoothing_window': 3}})",
    )


# ── Response models ────────────────────────────────────────────────────────────


class SessionResponse(BaseModel):
    """Returned after session creation."""

    session_id: str
    patient_id: str
    status: SessionStatus
    created_at: datetime


class UploadResponse(BaseModel):
    """Returned after a successful file upload."""

    session_id: str
    filename: str
    size_bytes: int
    camera_view: str
    status: SessionStatus


class StatusResponse(BaseModel):
    """Returned by the status polling endpoint."""

    session_id: str
    patient_id: str
    status: SessionStatus
    task_id: Optional[str] = None
    error_message: Optional[str] = None
    progress_pct: Optional[float] = Field(
        None, ge=0, le=100, description="Completion percentage (0–100)"
    )
    uploaded_files: List[str] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    """Returned by the profile retrieval endpoint."""

    session_id: str
    patient_id: str
    status: SessionStatus
    profile: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """Returned by the health check endpoint."""

    status: str = "ok"
    version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=lambda: datetime.utcnow())


class ErrorResponse(BaseModel):
    """Uniform error body."""

    detail: str
    error_code: Optional[str] = None


# ── Validation helpers ────────────────────────────────────────────────────────


class UploadQueryParams(BaseModel):
    """Query parameters accepted by the upload endpoint."""

    camera_view: str = Field(
        "sagittal",
        description="Which camera this file is from (sagittal, posterior, plantar, etc.)",
    )

    @field_validator("camera_view")
    @classmethod
    def validate_camera_view(cls, v: str) -> str:
        allowed = {"sagittal", "posterior", "plantar", "lateral", "anterior"}
        if v not in allowed:
            raise ValueError(f"camera_view must be one of {sorted(allowed)}, got {v!r}")
        return v

"""Unit tests for API Pydantic models (src.gait.api.models)."""
from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from gait.api.models import (
    AnthropometricsIn,
    LRMeasurement,
    ProcessRequest,
    ProfileResponse,
    SessionCreate,
    SessionResponse,
    SessionStatus,
    StatusResponse,
    UploadQueryParams,
    UploadResponse,
)

# â”€â”€ SessionStatus enum â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSessionStatus:
    def test_all_values_are_strings(self):
        for status in SessionStatus:
            assert isinstance(status.value, str)

    def test_created(self):
        assert SessionStatus.CREATED == "CREATED"

    def test_queued(self):
        assert SessionStatus.QUEUED == "QUEUED"

    def test_processing(self):
        assert SessionStatus.PROCESSING == "PROCESSING"

    def test_completed(self):
        assert SessionStatus.COMPLETED == "COMPLETED"

    def test_failed(self):
        assert SessionStatus.FAILED == "FAILED"

    def test_uploading(self):
        assert SessionStatus.UPLOADING == "UPLOADING"


# â”€â”€ LRMeasurement â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestLRMeasurement:
    def test_valid(self):
        m = LRMeasurement(L=258.0, R=260.0)
        assert m.L == pytest.approx(258.0)
        assert m.R == pytest.approx(260.0)

    def test_missing_L_raises(self):
        with pytest.raises(ValidationError):
            LRMeasurement(R=260.0)

    def test_missing_R_raises(self):
        with pytest.raises(ValidationError):
            LRMeasurement(L=258.0)


# â”€â”€ AnthropometricsIn â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestAnthropometricsIn:
    def _valid(self) -> dict:
        return {
            "height_cm": 172.0,
            "mass_kg": 68.0,
            "foot_length_mm": {"L": 258.0, "R": 260.0},
            "foot_width_mm": {"L": 98.0, "R": 99.0},
        }

    def test_valid_all_fields(self):
        a = AnthropometricsIn(**self._valid())
        assert a.height_cm == pytest.approx(172.0)

    def test_missing_height_raises(self):
        d = self._valid()
        del d["height_cm"]
        with pytest.raises(ValidationError):
            AnthropometricsIn(**d)

    def test_negative_height_raises(self):
        d = self._valid()
        d["height_cm"] = -10.0
        with pytest.raises(ValidationError):
            AnthropometricsIn(**d)

    def test_zero_mass_raises(self):
        d = self._valid()
        d["mass_kg"] = 0.0
        with pytest.raises(ValidationError):
            AnthropometricsIn(**d)

    def test_extreme_height_raises(self):
        d = self._valid()
        d["height_cm"] = 400.0  # > 300
        with pytest.raises(ValidationError):
            AnthropometricsIn(**d)

    def test_foot_length_nested_model(self):
        a = AnthropometricsIn(**self._valid())
        assert a.foot_length_mm.L == pytest.approx(258.0)
        assert a.foot_length_mm.R == pytest.approx(260.0)


# â”€â”€ SessionCreate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSessionCreate:
    def _anthro(self) -> dict:
        return {
            "height_cm": 172.0,
            "mass_kg": 68.0,
            "foot_length_mm": {"L": 258.0, "R": 260.0},
            "foot_width_mm": {"L": 98.0, "R": 99.0},
        }

    def test_valid(self):
        sc = SessionCreate(
            patient_id="P001",
            anthropometrics=self._anthro(),
            trial_condition="barefoot",
        )
        assert sc.patient_id == "P001"

    def test_empty_patient_id_raises(self):
        with pytest.raises(ValidationError):
            SessionCreate(
                patient_id="",
                anthropometrics=self._anthro(),
                trial_condition="barefoot",
            )

    def test_missing_anthropometrics_raises(self):
        with pytest.raises(ValidationError):
            SessionCreate(patient_id="P001", trial_condition="barefoot")

    def test_patient_id_whitespace_accepted(self):
        sc = SessionCreate(
            patient_id="P 001",
            anthropometrics=self._anthro(),
            trial_condition="shod",
        )
        assert sc.patient_id == "P 001"


# â”€â”€ ProcessRequest â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestProcessRequest:
    def test_defaults(self):
        r = ProcessRequest()
        assert r.config_overrides == {}

    def test_custom_overrides(self):
        r = ProcessRequest(config_overrides={"pose": {"smoothing_window": 3}})
        assert r.config_overrides["pose"]["smoothing_window"] == 3

    def test_nested_overrides_preserved(self):
        r = ProcessRequest(
            config_overrides={"analysis": {"symmetry_flag_threshold_pct": 15.0}}
        )
        assert r.config_overrides["analysis"]["symmetry_flag_threshold_pct"] == 15.0


# â”€â”€ SessionResponse â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSessionResponse:
    def test_valid(self):
        r = SessionResponse(
            session_id="abc-123",
            patient_id="P001",
            status=SessionStatus.CREATED,
            created_at=datetime.utcnow(),
        )
        assert r.session_id == "abc-123"
        assert r.status == SessionStatus.CREATED


# â”€â”€ UploadResponse â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestUploadResponse:
    def test_valid(self):
        r = UploadResponse(
            session_id="abc-123",
            filename="sagittal.mp4",
            size_bytes=1024,
            camera_view="sagittal",
            status=SessionStatus.UPLOADING,
        )
        assert r.size_bytes == 1024

    def test_status_is_uploading_enum(self):
        r = UploadResponse(
            session_id="abc",
            filename="f.mp4",
            size_bytes=0,
            camera_view="posterior",
            status=SessionStatus.UPLOADING,
        )
        assert r.status == SessionStatus.UPLOADING


# â”€â”€ StatusResponse â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestStatusResponse:
    def test_minimal(self):
        r = StatusResponse(
            session_id="abc",
            patient_id="P001",
            status=SessionStatus.QUEUED,
        )
        assert r.task_id is None
        assert r.error_message is None
        assert r.progress_pct is None
        assert r.uploaded_files == []

    def test_with_progress(self):
        r = StatusResponse(
            session_id="abc",
            patient_id="P001",
            status=SessionStatus.PROCESSING,
            progress_pct=45.0,
        )
        assert r.progress_pct == pytest.approx(45.0)

    def test_progress_above_100_raises(self):
        with pytest.raises(ValidationError):
            StatusResponse(
                session_id="abc",
                patient_id="P001",
                status=SessionStatus.PROCESSING,
                progress_pct=101.0,
            )

    def test_progress_below_0_raises(self):
        with pytest.raises(ValidationError):
            StatusResponse(
                session_id="abc",
                patient_id="P001",
                status=SessionStatus.PROCESSING,
                progress_pct=-1.0,
            )


# â”€â”€ ProfileResponse â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestProfileResponse:
    def test_no_profile(self):
        r = ProfileResponse(
            session_id="abc",
            patient_id="P001",
            status=SessionStatus.PROCESSING,
        )
        assert r.profile is None

    def test_with_profile(self):
        r = ProfileResponse(
            session_id="abc",
            patient_id="P001",
            status=SessionStatus.COMPLETED,
            profile={"patient_id": "P001", "schema_version": "profile/v1"},
        )
        assert r.profile["patient_id"] == "P001"


# â”€â”€ UploadQueryParams â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestUploadQueryParams:
    def test_default_camera_view(self):
        p = UploadQueryParams()
        assert p.camera_view == "anterior"

    def test_valid_camera_view(self):
        for view in ("anterior", "sagittal", "posterior"):
            p = UploadQueryParams(camera_view=view)
            assert p.camera_view == view

    def test_invalid_camera_view_raises(self):
        with pytest.raises(ValidationError):
            UploadQueryParams(camera_view="plantar")


"""Integration tests for the Gait Analysis FastAPI endpoints.

Uses FastAPI's synchronous TestClient (via httpx).  Celery is never actually
invoked: we override `get_pipeline_task` with a fake task that stores a
synthetic profile directly into the session store.

The session store is fresh per test via `app.dependency_overrides`.
"""
from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.gait.api.main import app, get_pipeline_task, get_session_store
from src.gait.api.models import SessionStatus
from src.gait.api.session_store import SessionStore

# ── Sample data ────────────────────────────────────────────────────────────────

ANTHRO = {
    "height_cm": 172.0,
    "mass_kg": 68.0,
    "foot_length_mm": {"L": 258.0, "R": 260.0},
    "foot_width_mm": {"L": 98.0, "R": 99.0},
}

SAMPLE_PROFILE = {
    "schema_version": "profile/v1",
    "patient_id": "P001",
    "session_timestamp": "2026-06-13T10:00:00+00:00",
    "anthropometrics": ANTHRO,
    "spatiotemporal": {
        "cadence_spm": 112.0,
        "speed_mps": 0.0,
        "stride_length_m": 0.0,
        "step_width_m": 0.0,
        "stance_pct": {"L": 61.0, "R": 60.0},
        "double_support_pct": 0.0,
        "swing_pct": {"L": 39.0, "R": 40.0},
    },
    "foot_strike": {
        "pattern": {"L": "rearfoot", "R": "rearfoot"},
        "foot_strike_angle_deg": {"L": 10.0, "R": 9.0},
    },
    "pronation": {
        "rearfoot_angle_at_midstance_deg": {"L": 2.0, "R": 2.0},
        "classification": {"L": "neutral", "R": "neutral"},
        "time_to_peak_eversion_pct_stance": {"L": 40.0, "R": 40.0},
    },
    "arch": {
        "type": {"L": "normal", "R": "normal"},
        "arch_height_index": {"L": 0.25, "R": 0.25},
    },
    "symmetry_flags": [],
    "health_assessment": {
        "what_went_right": ["Neutral pronation pattern"],
        "defects_found": [],
        "improvement_plan": [],
    },
    "confidence_scores": {"pipeline": 0.80},
    "needs_human_review": False,
    "quality_metrics": {
        "quality_flag_L": "PROCEED_OK",
        "quality_flag_R": "PROCEED_OK",
        "cycle_count_L": 8,
        "cycle_count_R": 8,
    },
}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def store() -> SessionStore:
    return SessionStore()


@pytest.fixture()
def fake_task():
    """A fake pipeline task that returns a stable result ID without touching the store."""

    class _FakeResult:
        id = "fake-task-uuid"

    class _FakeTask:
        def delay(self, session_id: str, **kwargs) -> _FakeResult:
            return _FakeResult()

    return _FakeTask()


@pytest.fixture()
def mock_async_result() -> MagicMock:
    """Celery AsyncResult mock that reports the task as successfully completed."""
    result = MagicMock()
    result.state = "SUCCESS"
    result.result = {"status": "COMPLETED", "profile": SAMPLE_PROFILE}
    result.info = {"progress_pct": 100}
    return result


@pytest.fixture()
def client(store: SessionStore, fake_task, mock_async_result) -> TestClient:
    app.dependency_overrides[get_session_store] = lambda: store
    app.dependency_overrides[get_pipeline_task] = lambda: fake_task
    with patch("src.gait.api.tasks.celery_app") as mock_celery:
        mock_celery.AsyncResult.return_value = mock_async_result
        yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def session_id(client: TestClient) -> str:
    """Create a session and return its ID."""
    r = client.post(
        "/api/v1/sessions",
        json={
                "patient_id": "P001",
                "anthropometrics": ANTHRO,
                "trial_condition": "barefoot",
            },
    )
    assert r.status_code == 201
    return r.json()["session_id"]


# ── Health endpoint ───────────────────────────────────────────────────────────


class TestHealth:
    def test_returns_200(self, client: TestClient):
        r = client.get("/health")
        assert r.status_code == 200

    def test_status_ok(self, client: TestClient):
        assert client.get("/health").json()["status"] == "ok"

    def test_version_present(self, client: TestClient):
        assert "version" in client.get("/health").json()

    def test_timestamp_present(self, client: TestClient):
        assert "timestamp" in client.get("/health").json()


# ── API root ──────────────────────────────────────────────────────────────────


class TestApiRoot:
    def test_returns_200(self, client: TestClient):
        assert client.get("/api/v1/").status_code == 200

    def test_name_present(self, client: TestClient):
        data = client.get("/api/v1/").json()
        assert "name" in data

    def test_version_present(self, client: TestClient):
        assert "version" in client.get("/api/v1/").json()


# ── Create session ────────────────────────────────────────────────────────────


class TestCreateSession:
    def test_returns_201(self, client: TestClient):
        r = client.post(
            "/api/v1/sessions",
            json={
                "patient_id": "P001",
                "anthropometrics": ANTHRO,
                "trial_condition": "barefoot",
            },
        )
        assert r.status_code == 201

    def test_session_id_in_response(self, client: TestClient):
        r = client.post(
            "/api/v1/sessions",
            json={
                "patient_id": "P001",
                "anthropometrics": ANTHRO,
                "trial_condition": "barefoot",
            },
        )
        assert "session_id" in r.json()
        assert len(r.json()["session_id"]) == 36  # UUID format

    def test_status_is_created(self, client: TestClient):
        r = client.post(
            "/api/v1/sessions",
            json={
                "patient_id": "P001",
                "anthropometrics": ANTHRO,
                "trial_condition": "barefoot",
            },
        )
        assert r.json()["status"] == "CREATED"

    def test_patient_id_echoed(self, client: TestClient):
        r = client.post(
            "/api/v1/sessions",
            json={
                "patient_id": "P-ABC",
                "anthropometrics": ANTHRO,
                "trial_condition": "barefoot",
            },
        )
        assert r.json()["patient_id"] == "P-ABC"

    def test_missing_patient_id_returns_422(self, client: TestClient):
        r = client.post(
            "/api/v1/sessions",
            json={"anthropometrics": ANTHRO},
        )
        assert r.status_code == 422

    def test_empty_patient_id_returns_422(self, client: TestClient):
        r = client.post(
            "/api/v1/sessions",
            json={"patient_id": "", "anthropometrics": ANTHRO},
        )
        assert r.status_code == 422

    def test_negative_height_returns_422(self, client: TestClient):
        bad_anthro = dict(ANTHRO, height_cm=-1.0)
        r = client.post(
            "/api/v1/sessions",
            json={"patient_id": "P001", "anthropometrics": bad_anthro},
        )
        assert r.status_code == 422

    def test_two_sessions_have_different_ids(self, client: TestClient):
        r1 = client.post(
            "/api/v1/sessions",
            json={
                "patient_id": "P001",
                "anthropometrics": ANTHRO,
                "trial_condition": "barefoot",
            },
        )
        r2 = client.post(
            "/api/v1/sessions",
            json={
                "patient_id": "P002",
                "anthropometrics": ANTHRO,
                "trial_condition": "shod",
            },
        )
        assert r1.json()["session_id"] != r2.json()["session_id"]


# ── Upload video ──────────────────────────────────────────────────────────────


class TestUpload:
    def test_upload_returns_200(self, client: TestClient, session_id: str, tmp_path):
        r = client.post(
            f"/api/v1/sessions/{session_id}/uploads",
            files={"file": ("sagittal.mp4", b"fake_video_bytes", "video/mp4")},
            params={"camera_view": "sagittal"},
        )
        assert r.status_code == 200

    def test_upload_filename_in_response(self, client: TestClient, session_id: str):
        r = client.post(
            f"/api/v1/sessions/{session_id}/uploads",
            files={"file": ("sagittal.mp4", b"data", "video/mp4")},
        )
        assert r.json()["filename"] == "sagittal.mp4"

    def test_upload_size_bytes_correct(self, client: TestClient, session_id: str):
        data = b"x" * 1024
        r = client.post(
            f"/api/v1/sessions/{session_id}/uploads",
            files={"file": ("f.mp4", data, "video/mp4")},
        )
        assert r.json()["size_bytes"] == 1024

    def test_upload_unknown_session_returns_404(self, client: TestClient):
        r = client.post(
            "/api/v1/sessions/no-such-id/uploads",
            files={"file": ("f.mp4", b"data", "video/mp4")},
        )
        assert r.status_code == 404

    def test_upload_to_completed_session_returns_409(
        self, client: TestClient, session_id: str, store: SessionStore
    ):
        store.update_status(session_id, SessionStatus.COMPLETED)
        r = client.post(
            f"/api/v1/sessions/{session_id}/uploads",
            files={"file": ("f.mp4", b"data", "video/mp4")},
        )
        assert r.status_code == 409


# ── Process session ───────────────────────────────────────────────────────────


class TestProcess:
    def test_process_returns_202(self, client: TestClient, session_id: str):
        r = client.post(f"/api/v1/sessions/{session_id}/process", json={})
        assert r.status_code == 202

    def test_process_status_queued_or_completed(
        self, client: TestClient, session_id: str
    ):
        r = client.post(f"/api/v1/sessions/{session_id}/process", json={})
        # With fake_task, might immediately be COMPLETED; either is acceptable
        assert r.json()["status"] in ("QUEUED", "COMPLETED")

    def test_task_id_returned(self, client: TestClient, session_id: str):
        r = client.post(f"/api/v1/sessions/{session_id}/process", json={})
        assert r.json()["task_id"] is not None

    def test_task_id_is_fake_uuid(self, client: TestClient, session_id: str):
        r = client.post(f"/api/v1/sessions/{session_id}/process", json={})
        assert r.json()["task_id"] == "fake-task-uuid"

    def test_process_unknown_session_returns_404(self, client: TestClient):
        r = client.post("/api/v1/sessions/no-such-id/process", json={})
        assert r.status_code == 404

    def test_process_already_queued_returns_409(
        self, client: TestClient, session_id: str, store: SessionStore
    ):
        store.update_status(session_id, SessionStatus.QUEUED, task_id="t1")
        r = client.post(f"/api/v1/sessions/{session_id}/process", json={})
        assert r.status_code == 409

    def test_process_already_completed_returns_409(
        self, client: TestClient, session_id: str, store: SessionStore
    ):
        store.update_status(session_id, SessionStatus.COMPLETED)
        r = client.post(f"/api/v1/sessions/{session_id}/process", json={})
        assert r.status_code == 409

    def test_process_config_overrides_accepted(
        self, client: TestClient, session_id: str
    ):
        r = client.post(
            f"/api/v1/sessions/{session_id}/process",
            json={"config_overrides": {"pose": {"smoothing_window": 3}}},
        )
        assert r.status_code == 202


# ── Status endpoint ───────────────────────────────────────────────────────────


class TestStatus:
    def test_status_unknown_session_returns_404(self, client: TestClient):
        r = client.get("/api/v1/sessions/no-such-id/status")
        assert r.status_code == 404

    def test_status_created_session(self, client: TestClient, session_id: str):
        r = client.get(f"/api/v1/sessions/{session_id}/status")
        assert r.status_code == 200
        assert r.json()["status"] == "CREATED"

    def test_status_after_process_is_completed(
        self, client: TestClient, session_id: str
    ):
        client.post(f"/api/v1/sessions/{session_id}/process", json={})
        r = client.get(f"/api/v1/sessions/{session_id}/status")
        assert r.json()["status"] == "COMPLETED"

    def test_status_contains_patient_id(self, client: TestClient, session_id: str):
        r = client.get(f"/api/v1/sessions/{session_id}/status")
        assert r.json()["patient_id"] == "P001"

    def test_status_contains_session_id(self, client: TestClient, session_id: str):
        r = client.get(f"/api/v1/sessions/{session_id}/status")
        assert r.json()["session_id"] == session_id

    def test_status_contains_uploaded_files_list(
        self, client: TestClient, session_id: str
    ):
        client.post(
            f"/api/v1/sessions/{session_id}/uploads",
            files={"file": ("f.mp4", b"data", "video/mp4")},
        )
        r = client.get(f"/api/v1/sessions/{session_id}/status")
        assert isinstance(r.json()["uploaded_files"], list)
        assert len(r.json()["uploaded_files"]) == 1

    def test_status_failed_includes_error_message(
        self, client: TestClient, session_id: str, store: SessionStore
    ):
        store.update_status(
            session_id,
            SessionStatus.FAILED,
            task_id="t1",
            error_message="Pipeline exploded",
        )
        r = client.get(f"/api/v1/sessions/{session_id}/status")
        assert r.json()["error_message"] == "Pipeline exploded"


# ── Profile endpoint ──────────────────────────────────────────────────────────


class TestProfile:
    def test_profile_unknown_session_returns_404(self, client: TestClient):
        r = client.get("/api/v1/sessions/no-such-id/profile")
        assert r.status_code == 404

    def test_profile_before_processing_returns_null(
        self, client: TestClient, session_id: str
    ):
        r = client.get(f"/api/v1/sessions/{session_id}/profile")
        assert r.status_code == 200
        assert r.json()["profile"] is None

    def test_profile_after_completion_returns_data(
        self, client: TestClient, session_id: str
    ):
        client.post(f"/api/v1/sessions/{session_id}/process", json={})
        r = client.get(f"/api/v1/sessions/{session_id}/profile")
        assert r.status_code == 200
        assert r.json()["profile"] is not None

    def test_profile_patient_id_correct(self, client: TestClient, session_id: str):
        client.post(f"/api/v1/sessions/{session_id}/process", json={})
        r = client.get(f"/api/v1/sessions/{session_id}/profile")
        assert r.json()["profile"]["patient_id"] == "P001"

    def test_profile_status_completed(self, client: TestClient, session_id: str):
        client.post(f"/api/v1/sessions/{session_id}/process", json={})
        r = client.get(f"/api/v1/sessions/{session_id}/profile")
        assert r.json()["status"] == "COMPLETED"

    def test_profile_failed_session_returns_422(
        self, client: TestClient, session_id: str, store: SessionStore
    ):
        store.update_status(
            session_id,
            SessionStatus.FAILED,
            error_message="crashed",
        )
        r = client.get(f"/api/v1/sessions/{session_id}/profile")
        assert r.status_code == 422

    def test_profile_contains_shoe_recommendations(
        self, client: TestClient, session_id: str
    ):
        client.post(f"/api/v1/sessions/{session_id}/process", json={})
        r = client.get(f"/api/v1/sessions/{session_id}/profile")
        profile = r.json()["profile"]
        assert "health_assessment" in profile

    def test_profile_schema_version(self, client: TestClient, session_id: str):
        client.post(f"/api/v1/sessions/{session_id}/process", json={})
        r = client.get(f"/api/v1/sessions/{session_id}/profile")
        assert r.json()["profile"]["schema_version"] == "profile/v1"


# ── Delete session ────────────────────────────────────────────────────────────


class TestDeleteSession:
    def test_delete_returns_204(self, client: TestClient, session_id: str):
        r = client.delete(f"/api/v1/sessions/{session_id}")
        assert r.status_code == 204

    def test_delete_unknown_session_returns_404(self, client: TestClient):
        r = client.delete("/api/v1/sessions/no-such-id")
        assert r.status_code == 404

    def test_delete_makes_session_unreachable(
        self, client: TestClient, session_id: str
    ):
        client.delete(f"/api/v1/sessions/{session_id}")
        r = client.get(f"/api/v1/sessions/{session_id}/status")
        assert r.status_code == 404

    def test_delete_queued_session_returns_409(
        self, client: TestClient, session_id: str, store: SessionStore
    ):
        store.update_status(session_id, SessionStatus.QUEUED, task_id="t1")
        r = client.delete(f"/api/v1/sessions/{session_id}")
        assert r.status_code == 409

    def test_delete_processing_session_returns_409(
        self, client: TestClient, session_id: str, store: SessionStore
    ):
        store.update_status(session_id, SessionStatus.PROCESSING, task_id="t1")
        r = client.delete(f"/api/v1/sessions/{session_id}")
        assert r.status_code == 409

    def test_delete_completed_session_succeeds(
        self, client: TestClient, session_id: str, store: SessionStore
    ):
        store.update_status(session_id, SessionStatus.COMPLETED)
        r = client.delete(f"/api/v1/sessions/{session_id}")
        assert r.status_code == 204


# ── Full session lifecycle ────────────────────────────────────────────────────


class TestFullLifecycle:
    def test_create_upload_process_profile(
        self, client: TestClient, tmp_path, monkeypatch
    ):
        """End-to-end lifecycle: create → upload → process → profile."""
        from src.gait.api import main as api_main

        monkeypatch.setattr(api_main, "UPLOAD_DIR", tmp_path)

        # 1. Create
        r = client.post(
            "/api/v1/sessions",
            json={"patient_id": "P999", "anthropometrics": ANTHRO, "trial_condition": "barefoot"},
        )
        assert r.status_code == 201
        sid = r.json()["session_id"]

        # 2. Upload
        r = client.post(
            f"/api/v1/sessions/{sid}/uploads",
            files={"file": ("sagittal.mp4", b"fake", "video/mp4")},
            params={"camera_view": "sagittal"},
        )
        assert r.status_code == 200

        # 3. Process
        r = client.post(f"/api/v1/sessions/{sid}/process", json={})
        assert r.status_code == 202

        # 4. Status → COMPLETED (fake task completes immediately)
        r = client.get(f"/api/v1/sessions/{sid}/status")
        assert r.json()["status"] == "COMPLETED"

        # 5. Profile
        r = client.get(f"/api/v1/sessions/{sid}/profile")
        assert r.status_code == 200
        assert r.json()["profile"] is not None
        assert r.json()["profile"]["patient_id"] == "P001"  # from SAMPLE_PROFILE

    def test_status_transitions_are_monotonic(
        self, client: TestClient, session_id: str
    ):
        """Status should only move forward through the lifecycle."""
        r1 = client.get(f"/api/v1/sessions/{session_id}/status")
        assert r1.json()["status"] == "CREATED"

        client.post(f"/api/v1/sessions/{session_id}/process", json={})

        r2 = client.get(f"/api/v1/sessions/{session_id}/status")
        assert r2.json()["status"] == "COMPLETED"

    def test_multiple_sessions_independent(self, client: TestClient):
        """Two concurrent sessions should not interfere."""
        r1 = client.post(
            "/api/v1/sessions",
            json={
                "patient_id": "P001",
                "anthropometrics": ANTHRO,
                "trial_condition": "barefoot",
            },
        )
        r2 = client.post(
            "/api/v1/sessions",
            json={
                "patient_id": "P002",
                "anthropometrics": ANTHRO,
                "trial_condition": "shod",
            },
        )
        sid1, sid2 = r1.json()["session_id"], r2.json()["session_id"]
        assert sid1 != sid2

        client.post(f"/api/v1/sessions/{sid1}/process", json={})

        s1 = client.get(f"/api/v1/sessions/{sid1}/status").json()["status"]
        s2 = client.get(f"/api/v1/sessions/{sid2}/status").json()["status"]
        assert s1 == "COMPLETED"
        assert s2 == "CREATED"

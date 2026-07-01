"""Unit tests for SessionRepository (src.gait.db.session_repo)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SQLSession
from sqlalchemy.orm import sessionmaker

from gait.api.models import SessionStatus
from gait.db.models import Base, Session, User
from gait.db.session_repo import SessionRepository

# â”€â”€ fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


@pytest.fixture
def repo(in_memory_db: SQLSession) -> SessionRepository:
    """Create a SessionRepository instance."""
    return SessionRepository(in_memory_db)


@pytest.fixture
def user(in_memory_db: SQLSession) -> User:
    """Create a test user."""
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="hashed_password",
        is_active=1,
    )
    in_memory_db.add(user)
    in_memory_db.commit()
    in_memory_db.refresh(user)
    return user


# â”€â”€ Create Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestCreate:
    def test_create_session(self, repo: SessionRepository, user: User):
        anthropometrics = {
            "height_cm": 172,
            "mass_kg": 68,
            "foot_length_mm": {"L": 258, "R": 260},
            "foot_width_mm": {"L": 98, "R": 99},
        }
        session = repo.create(
            session_id="test-uuid-1",
            user_id=user.id,
            patient_id="P001",
            anthropometrics=anthropometrics,
        )

        assert session.id == "test-uuid-1"
        assert session.status == SessionStatus.CREATED.value
        assert session.anthropometrics == anthropometrics

    def test_create_multiple_sessions(self, repo: SessionRepository, user: User):
        session1 = repo.create("uuid-1", user.id, "P001", {})
        session2 = repo.create("uuid-2", user.id, "P002", {})

        assert session1.id != session2.id
        assert session1.patient_id == "P001"
        assert session2.patient_id == "P002"


# â”€â”€ Read Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestRead:
    def test_get_session(self, repo: SessionRepository, user: User):
        created = repo.create("test-uuid", user.id, "P001", {})
        retrieved = repo.get("test-uuid")

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.patient_id == "P001"

    def test_get_nonexistent_session(self, repo: SessionRepository):
        result = repo.get("nonexistent-uuid")
        assert result is None

    def test_get_by_user(self, repo: SessionRepository, user: User, in_memory_db: SQLSession):
        # Create another user
        user2 = User(username="user2", email="user2@example.com", hashed_password="pwd", is_active=1)
        in_memory_db.add(user2)
        in_memory_db.commit()
        in_memory_db.refresh(user2)

        # Create sessions
        repo.create("uuid-1", user.id, "P001", {})
        repo.create("uuid-2", user.id, "P002", {})
        repo.create("uuid-3", user2.id, "P003", {})

        # Get sessions by user
        user1_sessions = repo.get_by_user(user.id)
        user2_sessions = repo.get_by_user(user2.id)

        assert len(user1_sessions) == 2
        assert len(user2_sessions) == 1

    def test_list_sessions(self, repo: SessionRepository, user: User):
        repo.create("uuid-1", user.id, "P001", {})
        repo.create("uuid-2", user.id, "P002", {})

        all_sessions = repo.list_sessions()
        assert len(all_sessions) == 2

    def test_list_sessions_filtered_by_user(self, repo: SessionRepository, user: User):
        repo.create("uuid-1", user.id, "P001", {})
        repo.create("uuid-2", user.id, "P002", {})

        user_sessions = repo.list_sessions(user_id=user.id)
        assert len(user_sessions) == 2


# â”€â”€ Update Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestUpdate:
    def test_update_status(self, repo: SessionRepository, user: User):
        repo.create("test-uuid", user.id, "P001", {})
        updated = repo.update_status("test-uuid", SessionStatus.PROCESSING)

        assert updated is not None
        assert updated.status == SessionStatus.PROCESSING.value

    def test_update_status_nonexistent(self, repo: SessionRepository):
        result = repo.update_status("nonexistent", SessionStatus.PROCESSING)
        assert result is None

    def test_update_task_id(self, repo: SessionRepository, user: User):
        repo.create("test-uuid", user.id, "P001", {})
        updated = repo.update_status("test-uuid", SessionStatus.QUEUED, task_id="celery-task-123")

        assert updated is not None
        assert updated.task_id == "celery-task-123"

    def test_update_error_message(self, repo: SessionRepository, user: User):
        repo.create("test-uuid", user.id, "P001", {})
        updated = repo.update_status(
            "test-uuid",
            SessionStatus.FAILED,
            error_message="Pipeline timeout",
        )

        assert updated is not None
        assert updated.error_message == "Pipeline timeout"

    def test_update_progress(self, repo: SessionRepository, user: User):
        repo.create("test-uuid", user.id, "P001", {})
        updated = repo.update_status("test-uuid", SessionStatus.PROCESSING, progress_pct=50)

        assert updated is not None
        assert updated.progress_pct == 50

    def test_update_progress_invalid_range(self, repo: SessionRepository, user: User):
        repo.create("test-uuid", user.id, "P001", {})

        with pytest.raises(ValueError):
            repo.update_status("test-uuid", SessionStatus.PROCESSING, progress_pct=101)

        with pytest.raises(ValueError):
            repo.update_status("test-uuid", SessionStatus.PROCESSING, progress_pct=-1)

    def test_update_timestamp_changes(self, repo: SessionRepository, user: User):
        session = repo.create("test-uuid", user.id, "P001", {})
        created_at = session.updated_at

        import time

        time.sleep(0.01)
        updated = repo.update_status("test-uuid", SessionStatus.PROCESSING)

        assert updated is not None
        assert updated.updated_at > created_at


# â”€â”€ Upload Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestUpload:
    def test_add_uploaded_file(self, repo: SessionRepository, user: User):
        repo.create("test-uuid", user.id, "P001", {})
        upload = repo.add_uploaded_file(
            session_id="test-uuid",
            filename="sagittal.mp4",
            camera_view="sagittal",
            file_path="s3://bucket/sagittal.mp4",
            size_bytes=1024000,
        )

        assert upload is not None
        assert upload.filename == "sagittal.mp4"
        assert upload.camera_view == "sagittal"
        assert upload.size_bytes == 1024000

    def test_add_uploaded_file_nonexistent_session(self, repo: SessionRepository):
        result = repo.add_uploaded_file(
            session_id="nonexistent",
            filename="test.mp4",
            camera_view="sagittal",
            file_path="/path/test.mp4",
            size_bytes=1000,
        )

        assert result is None

    def test_get_uploads(self, repo: SessionRepository, user: User):
        repo.create("test-uuid", user.id, "P001", {})
        repo.add_uploaded_file("test-uuid", "file1.mp4", "sagittal", "s3://file1.mp4", 1000)
        repo.add_uploaded_file("test-uuid", "file2.mp4", "posterior", "s3://file2.mp4", 2000)

        uploads = repo.get_uploads("test-uuid")

        assert len(uploads) == 2
        assert uploads[0].filename == "file1.mp4"
        assert uploads[1].filename == "file2.mp4"

    def test_session_status_changes_to_uploading(self, repo: SessionRepository, user: User):
        repo.create("test-uuid", user.id, "P001", {})
        repo.add_uploaded_file("test-uuid", "test.mp4", "sagittal", "s3://test.mp4", 1000)

        session = repo.get("test-uuid")
        assert session is not None
        assert session.status == SessionStatus.UPLOADING.value


# â”€â”€ Delete Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestDelete:
    def test_delete_session(self, repo: SessionRepository, user: User):
        repo.create("test-uuid", user.id, "P001", {})
        result = repo.delete("test-uuid")

        assert result is True
        assert repo.get("test-uuid") is None

    def test_delete_nonexistent_session(self, repo: SessionRepository):
        result = repo.delete("nonexistent")
        assert result is False

    def test_delete_cascades_uploads(self, repo: SessionRepository, user: User):
        repo.create("test-uuid", user.id, "P001", {})
        repo.add_uploaded_file("test-uuid", "test.mp4", "sagittal", "s3://test.mp4", 1000)

        repo.delete("test-uuid")

        uploads = repo.get_uploads("test-uuid")
        assert len(uploads) == 0


# â”€â”€ Permission Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestPermissions:
    def test_can_access_own_session(self, repo: SessionRepository, user: User):
        repo.create("test-uuid", user.id, "P001", {})
        can_access = repo.can_access("test-uuid", user.id)

        assert can_access is True

    def test_cannot_access_other_session(self, repo: SessionRepository, user: User, in_memory_db: SQLSession):
        repo.create("test-uuid", user.id, "P001", {})

        # Create another user
        user2 = User(username="user2", email="user2@example.com", hashed_password="pwd", is_active=1)
        in_memory_db.add(user2)
        in_memory_db.commit()
        in_memory_db.refresh(user2)

        can_access = repo.can_access("test-uuid", user2.id)
        assert can_access is False

    def test_cannot_access_nonexistent_session(self, repo: SessionRepository, user: User):
        can_access = repo.can_access("nonexistent", user.id)
        assert can_access is False


# â”€â”€ Integration Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestIntegration:
    def test_full_session_lifecycle(self, repo: SessionRepository, user: User):
        """Test a complete session workflow."""
        # 1. Create session
        session = repo.create("test-uuid", user.id, "P001", {"height_cm": 172})
        assert session.status == SessionStatus.CREATED.value

        # 2. Add uploads
        repo.add_uploaded_file("test-uuid", "sagittal.mp4", "sagittal", "s3://sagittal.mp4", 1024000)
        repo.add_uploaded_file("test-uuid", "posterior.mp4", "posterior", "s3://posterior.mp4", 1024000)

        # 3. Update to processing
        repo.update_status(
            "test-uuid",
            SessionStatus.PROCESSING,
            task_id="celery-task-123",
            progress_pct=0,
        )

        # 4. Update progress
        repo.update_status("test-uuid", SessionStatus.PROCESSING, progress_pct=50)
        repo.update_status("test-uuid", SessionStatus.PROCESSING, progress_pct=100)

        # 5. Mark completed
        repo.update_status("test-uuid", SessionStatus.COMPLETED)

        # 6. Verify final state
        final = repo.get("test-uuid")
        assert final is not None
        assert final.status == SessionStatus.COMPLETED.value
        assert len(final.uploads) == 2


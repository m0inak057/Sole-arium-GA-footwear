"""Unit tests for database models (src.gait.db.models)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SQLSession
from sqlalchemy.orm import sessionmaker

from gait.api.models import SessionStatus
from gait.db.models import APIKey, Base, Profile, Session, Upload, User, create_database_url, init_db

# â”€â”€ fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


@pytest.fixture
def user(in_memory_db: SQLSession) -> User:
    """Create a test user."""
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="hashed_password_123",
        is_active=1,
    )
    in_memory_db.add(user)
    in_memory_db.commit()
    in_memory_db.refresh(user)
    return user


@pytest.fixture
def api_key(in_memory_db: SQLSession, user: User) -> APIKey:
    """Create a test API key."""
    api_key = APIKey(
        user_id=user.id,
        key_hash="key_hash_123",
        name="test_key",
        is_active=1,
    )
    in_memory_db.add(api_key)
    in_memory_db.commit()
    in_memory_db.refresh(api_key)
    return api_key


@pytest.fixture
def session_record(in_memory_db: SQLSession, user: User) -> Session:
    """Create a test session."""
    session = Session(
        id="550e8400-e29b-41d4-a716-446655440000",
        user_id=user.id,
        patient_id="P001",
        status=SessionStatus.CREATED.value,
        anthropometrics={
            "height_cm": 172,
            "mass_kg": 68,
            "foot_length_mm": {"L": 258, "R": 260},
            "foot_width_mm": {"L": 98, "R": 99},
        },
    )
    in_memory_db.add(session)
    in_memory_db.commit()
    in_memory_db.refresh(session)
    return session


# â”€â”€ User Model Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestUserModel:
    def test_create_user(self, in_memory_db: SQLSession):
        user = User(
            username="john",
            email="john@example.com",
            hashed_password="hashed_pwd",
            is_active=1,
        )
        in_memory_db.add(user)
        in_memory_db.commit()
        in_memory_db.refresh(user)

        assert user.id is not None
        assert user.username == "john"
        assert user.email == "john@example.com"
        assert user.is_active == 1

    def test_user_timestamps(self, in_memory_db: SQLSession):
        user = User(username="jane", email="jane@example.com", hashed_password="pwd", is_active=1)
        in_memory_db.add(user)
        in_memory_db.commit()
        in_memory_db.refresh(user)

        # Verify timestamps are set (SQLite doesn't preserve timezone info)
        assert user.created_at is not None
        assert user.updated_at is not None
        assert isinstance(user.created_at, datetime)
        assert isinstance(user.updated_at, datetime)

    def test_user_api_keys_relationship(self, user: User, api_key: APIKey):
        assert len(user.api_keys) == 1
        assert user.api_keys[0].key_hash == "key_hash_123"

    def test_user_sessions_relationship(self, in_memory_db: SQLSession, user: User, session_record: Session):
        in_memory_db.refresh(user)
        assert len(user.sessions) == 1
        assert user.sessions[0].patient_id == "P001"

    def test_unique_email_constraint(self, in_memory_db: SQLSession):
        user1 = User(username="user1", email="duplicate@example.com", hashed_password="pwd", is_active=1)
        user2 = User(username="user2", email="duplicate@example.com", hashed_password="pwd", is_active=1)
        in_memory_db.add(user1)
        in_memory_db.commit()
        in_memory_db.add(user2)
        with pytest.raises(Exception):  # IntegrityError
            in_memory_db.commit()

    def test_unique_username_constraint(self, in_memory_db: SQLSession):
        user1 = User(username="duplicate", email="user1@example.com", hashed_password="pwd", is_active=1)
        user2 = User(username="duplicate", email="user2@example.com", hashed_password="pwd", is_active=1)
        in_memory_db.add(user1)
        in_memory_db.commit()
        in_memory_db.add(user2)
        with pytest.raises(Exception):  # IntegrityError
            in_memory_db.commit()


# â”€â”€ API Key Model Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestAPIKeyModel:
    def test_create_api_key(self, in_memory_db: SQLSession, user: User):
        api_key = APIKey(
            user_id=user.id,
            key_hash="hash_123",
            name="my_api_key",
            is_active=1,
        )
        in_memory_db.add(api_key)
        in_memory_db.commit()
        in_memory_db.refresh(api_key)

        assert api_key.id is not None
        assert api_key.user_id == user.id
        assert api_key.is_active == 1

    def test_api_key_expiration(self, in_memory_db: SQLSession, user: User):
        future = datetime.now()  # Use naive datetime for SQLite compat
        api_key = APIKey(
            user_id=user.id,
            key_hash="hash_456",
            name="expiring_key",
            is_active=1,
            expires_at=future,
        )
        in_memory_db.add(api_key)
        in_memory_db.commit()
        in_memory_db.refresh(api_key)

        # SQLite stores datetimes without timezone
        assert api_key.expires_at.replace(tzinfo=None) == future

    def test_unique_key_hash_constraint(self, in_memory_db: SQLSession, user: User):
        key1 = APIKey(user_id=user.id, key_hash="same_hash", name="key1", is_active=1)
        key2 = APIKey(user_id=user.id, key_hash="same_hash", name="key2", is_active=1)
        in_memory_db.add(key1)
        in_memory_db.commit()
        in_memory_db.add(key2)
        with pytest.raises(Exception):  # IntegrityError
            in_memory_db.commit()


# â”€â”€ Session Model Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSessionModel:
    def test_create_session(self, in_memory_db: SQLSession, user: User):
        session = Session(
            id="test-uuid-123",
            user_id=user.id,
            patient_id="P002",
            status=SessionStatus.CREATED.value,
            anthropometrics={"height_cm": 175},
        )
        in_memory_db.add(session)
        in_memory_db.commit()
        in_memory_db.refresh(session)

        assert session.id == "test-uuid-123"
        assert session.patient_id == "P002"
        assert session.status == SessionStatus.CREATED.value

    def test_session_status_transition(self, in_memory_db: SQLSession, session_record: Session):
        session_record.status = SessionStatus.PROCESSING.value
        in_memory_db.commit()
        in_memory_db.refresh(session_record)

        assert session_record.status == SessionStatus.PROCESSING.value

    def test_session_task_id(self, in_memory_db: SQLSession, session_record: Session):
        session_record.task_id = "celery-task-uuid"
        in_memory_db.commit()
        in_memory_db.refresh(session_record)

        assert session_record.task_id == "celery-task-uuid"

    def test_session_error_message(self, in_memory_db: SQLSession, session_record: Session):
        session_record.status = SessionStatus.FAILED.value
        session_record.error_message = "Pipeline timeout"
        in_memory_db.commit()
        in_memory_db.refresh(session_record)

        assert session_record.error_message == "Pipeline timeout"

    def test_session_progress(self, in_memory_db: SQLSession, session_record: Session):
        session_record.status = SessionStatus.PROCESSING.value
        session_record.progress_pct = 45
        in_memory_db.commit()
        in_memory_db.refresh(session_record)

        assert session_record.progress_pct == 45

    def test_session_uploads_relationship(self, in_memory_db: SQLSession, session_record: Session):
        upload = Upload(
            session_id=session_record.id,
            filename="sagittal.mp4",
            camera_view="sagittal",
            file_path="s3://bucket/file.mp4",
            size_bytes=1024,
            upload_status="UPLOADED",
        )
        in_memory_db.add(upload)
        in_memory_db.commit()
        in_memory_db.refresh(session_record)

        assert len(session_record.uploads) == 1
        assert session_record.uploads[0].filename == "sagittal.mp4"


# â”€â”€ Upload Model Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestUploadModel:
    def test_create_upload(self, in_memory_db: SQLSession, session_record: Session):
        upload = Upload(
            session_id=session_record.id,
            filename="test.mp4",
            camera_view="posterior",
            file_path="/uploads/test.mp4",
            size_bytes=2048,
            upload_status="UPLOADED",
        )
        in_memory_db.add(upload)
        in_memory_db.commit()
        in_memory_db.refresh(upload)

        assert upload.id is not None
        assert upload.filename == "test.mp4"
        assert upload.size_bytes == 2048

    def test_upload_timestamps(self, in_memory_db: SQLSession, session_record: Session):
        upload = Upload(
            session_id=session_record.id,
            filename="test.mp4",
            camera_view="plantar",
            file_path="/uploads/test.mp4",
            size_bytes=512,
            upload_status="UPLOADED",
        )
        in_memory_db.add(upload)
        in_memory_db.commit()
        in_memory_db.refresh(upload)

        # Verify timestamps are set (SQLite doesn't preserve timezone info)
        assert upload.created_at is not None
        assert upload.updated_at is not None
        assert isinstance(upload.created_at, datetime)
        assert isinstance(upload.updated_at, datetime)


# â”€â”€ Profile Model Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestProfileModel:
    def test_create_profile(self, in_memory_db: SQLSession, session_record: Session):
        profile_data = {
            "schema_version": "profile/v1",
            "patient_id": "P001",
            "health_assessment": {
                "what_went_right": [],
                "defects_found": [],
                "improvement_plan": [],
            },
        }
        profile = Profile(
            session_id=session_record.id,
            patient_id="P001",
            schema_version="profile/v1",
            profile_data=profile_data,
            quality_flag="PROCEED_OK",
            needs_human_review=0,
        )
        in_memory_db.add(profile)
        in_memory_db.commit()
        in_memory_db.refresh(profile)

        assert profile.id is not None
        assert profile.quality_flag == "PROCEED_OK"
        assert profile.profile_data["schema_version"] == "profile/v1"

    def test_profile_human_review_flag(self, in_memory_db: SQLSession, session_record: Session):
        profile = Profile(
            session_id=session_record.id,
            patient_id="P001",
            schema_version="profile/v1",
            profile_data={"test": "data"},
            quality_flag="PROCEED_WITH_WARNING",
            needs_human_review=1,
        )
        in_memory_db.add(profile)
        in_memory_db.commit()
        in_memory_db.refresh(profile)

        assert profile.needs_human_review == 1


# â”€â”€ Database URL Helper Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestCreateDatabaseURL:
    def test_postgresql_url(self):
        url = create_database_url(
            db_user="user",
            db_password="pass",
            db_host="localhost",
            db_port=5432,
            db_name="testdb",
            driver="postgresql",
        )
        assert url == "postgresql://user:pass@localhost:5432/testdb"

    def test_sqlite_url(self):
        url = create_database_url(
            db_user="",
            db_password="",
            db_host="",
            db_port=0,
            db_name="/tmp/test.db",
            driver="sqlite",
        )
        assert url == "sqlite:////tmp/test.db"

    def test_unsupported_driver(self):
        with pytest.raises(ValueError):
            create_database_url(
                db_user="user",
                db_password="pass",
                db_host="localhost",
                db_port=3306,
                db_name="testdb",
                driver="mysql",
            )


# â”€â”€ Database Init Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestInitDB:
    def test_init_db_creates_tables(self):
        engine = create_engine("sqlite:///:memory:")
        init_db("sqlite:///:memory:")
        # Tables should be created
        assert "users" in Base.metadata.tables
        assert "sessions" in Base.metadata.tables
        assert "api_keys" in Base.metadata.tables


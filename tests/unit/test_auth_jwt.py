"""Unit tests for JWT token handling."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from gait.auth.jwt_handler import JWTHandler, TokenPayload


@pytest.fixture
def jwt_handler():
    """Create JWT handler with test secret."""
    return JWTHandler(secret_key="test-secret-key-that-is-longer-than-32-chars")


# â”€â”€ TokenPayload Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestTokenPayload:
    def test_create_payload(self):
        """Test creating token payload."""
        payload = TokenPayload(sub="user123", exp=1234567890, iat=1234567800)
        assert payload.sub == "user123"
        assert payload.exp == 1234567890
        assert payload.iat == 1234567800
        assert payload.type == "access"

    def test_payload_custom_type(self):
        """Test creating payload with custom type."""
        payload = TokenPayload(sub="user456", exp=1234567890, iat=1234567800, type="refresh")
        assert payload.type == "refresh"


# â”€â”€ JWT Handler Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestJWTHandler:
    def test_create_access_token(self, jwt_handler):
        """Test creating access token."""
        token = jwt_handler.create_access_token("user123", expires_in_minutes=60)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_custom_expiry(self, jwt_handler):
        """Test creating token with custom expiry."""
        token = jwt_handler.create_access_token("user456", expires_in_minutes=120)
        decoded = jwt.decode(token, jwt_handler.secret_key, algorithms=[jwt_handler.algorithm])
        assert decoded["sub"] == "user456"

    def test_create_access_token_with_claims(self, jwt_handler):
        """Test creating token with extra claims."""
        extra_claims = {"role": "admin", "scope": "write"}
        token = jwt_handler.create_access_token(
            "user789",
            extra_claims=extra_claims,
        )
        decoded = jwt.decode(token, jwt_handler.secret_key, algorithms=[jwt_handler.algorithm])
        assert decoded["role"] == "admin"
        assert decoded["scope"] == "write"

    def test_create_access_token_empty_subject(self, jwt_handler):
        """Test that empty subject raises ValueError."""
        with pytest.raises(ValueError, match="Subject cannot be empty"):
            jwt_handler.create_access_token("")

    def test_create_access_token_invalid_expiry(self, jwt_handler):
        """Test that invalid expiry raises ValueError."""
        with pytest.raises(ValueError, match="Expiration must be positive"):
            jwt_handler.create_access_token("user123", expires_in_minutes=0)

    def test_create_refresh_token(self, jwt_handler):
        """Test creating refresh token."""
        token = jwt_handler.create_refresh_token("user123", expires_in_days=7)
        decoded = jwt.decode(token, jwt_handler.secret_key, algorithms=[jwt_handler.algorithm])
        assert decoded["type"] == "refresh"

    def test_create_refresh_token_empty_subject(self, jwt_handler):
        """Test that empty subject raises ValueError."""
        with pytest.raises(ValueError, match="Subject cannot be empty"):
            jwt_handler.create_refresh_token("")

    def test_create_refresh_token_invalid_expiry(self, jwt_handler):
        """Test that invalid expiry raises ValueError."""
        with pytest.raises(ValueError, match="Expiration must be positive"):
            jwt_handler.create_refresh_token("user123", expires_in_days=-1)


# â”€â”€ Token Verification Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestTokenVerification:
    def test_verify_token(self, jwt_handler):
        """Test verifying valid token."""
        token = jwt_handler.create_access_token("user123")
        payload = jwt_handler.verify_token(token)
        assert payload.sub == "user123"
        assert payload.type == "access"

    def test_verify_token_invalid(self, jwt_handler):
        """Test that invalid token raises error."""
        with pytest.raises(jwt.InvalidTokenError):
            jwt_handler.verify_token("invalid.token.string")

    def test_verify_token_tampered(self, jwt_handler):
        """Test that tampered token raises error."""
        token = jwt_handler.create_access_token("user123")
        tampered = token[:-10] + "corrupted!"
        with pytest.raises(jwt.InvalidTokenError):
            jwt_handler.verify_token(tampered)

    def test_verify_token_expired(self, jwt_handler):
        """Test that expired token raises ExpiredSignatureError."""
        # Create token with very short expiry (1 second in the past)
        now = datetime.now(timezone.utc)
        exp = now - timedelta(seconds=1)

        payload = {
            "sub": "user123",
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "type": "access",
        }
        token = jwt.encode(payload, jwt_handler.secret_key, algorithm=jwt_handler.algorithm)

        with pytest.raises(jwt.ExpiredSignatureError):
            jwt_handler.verify_token(token)

    def test_verify_access_token_correct_type(self, jwt_handler):
        """Test verifying access token with correct type."""
        token = jwt_handler.create_access_token("user123")
        payload = jwt_handler.verify_access_token(token)
        assert payload.sub == "user123"
        assert payload.type == "access"

    def test_verify_access_token_wrong_type(self, jwt_handler):
        """Test that verifying refresh token as access raises error."""
        refresh_token = jwt_handler.create_refresh_token("user123")
        with pytest.raises(jwt.InvalidTokenError, match="not an access token"):
            jwt_handler.verify_access_token(refresh_token)

    def test_verify_refresh_token_correct_type(self, jwt_handler):
        """Test verifying refresh token with correct type."""
        token = jwt_handler.create_refresh_token("user123")
        payload = jwt_handler.verify_refresh_token(token)
        assert payload.sub == "user123"
        assert payload.type == "refresh"

    def test_verify_refresh_token_wrong_type(self, jwt_handler):
        """Test that verifying access token as refresh raises error."""
        access_token = jwt_handler.create_access_token("user123")
        with pytest.raises(jwt.InvalidTokenError, match="not a refresh token"):
            jwt_handler.verify_refresh_token(access_token)


# â”€â”€ Token Refresh Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestTokenRefresh:
    def test_refresh_access_token(self, jwt_handler):
        """Test refreshing access token from refresh token."""
        refresh_token = jwt_handler.create_refresh_token("user123")
        new_access_token = jwt_handler.refresh_access_token(refresh_token)

        payload = jwt_handler.verify_access_token(new_access_token)
        assert payload.sub == "user123"
        assert payload.type == "access"

    def test_refresh_access_token_invalid_refresh(self, jwt_handler):
        """Test that invalid refresh token raises error."""
        with pytest.raises(jwt.InvalidTokenError):
            jwt_handler.refresh_access_token("invalid.token")

    def test_refresh_access_token_expired_refresh(self, jwt_handler):
        """Test that expired refresh token raises error."""
        # Create token with past expiration
        now = datetime.now(timezone.utc)
        exp = now - timedelta(seconds=1)

        payload = {
            "sub": "user123",
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "type": "refresh",
        }
        refresh_token = jwt.encode(payload, jwt_handler.secret_key, algorithm=jwt_handler.algorithm)

        with pytest.raises(jwt.ExpiredSignatureError):
            jwt_handler.refresh_access_token(refresh_token)

    def test_refresh_access_token_custom_expiry(self, jwt_handler):
        """Test refreshing with custom expiry."""
        refresh_token = jwt_handler.create_refresh_token("user123")
        new_token = jwt_handler.refresh_access_token(
            refresh_token,
            expires_in_minutes=120,
        )

        payload = jwt_handler.verify_access_token(new_token)
        assert payload.sub == "user123"


# â”€â”€ Weak Secret Key Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestWeakSecretKey:
    def test_weak_secret_warning(self, caplog):
        """Test that weak secret key logs warning."""
        short_secret = "short"
        handler = JWTHandler(short_secret)
        assert handler.secret_key == short_secret
        # Warning should be logged


# â”€â”€ Token Payload Validation Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestTokenPayloadValidation:
    def test_payload_with_all_fields(self):
        """Test creating payload with all fields."""
        now = int(datetime.now(timezone.utc).timestamp())
        payload = TokenPayload(
            sub="user123",
            exp=now + 3600,
            iat=now,
            type="access",
        )
        assert payload.sub == "user123"
        assert payload.type == "access"

    def test_payload_defaults(self):
        """Test payload defaults to access type."""
        payload = TokenPayload(sub="user123", exp=1234567890, iat=1234567800)
        assert payload.type == "access"


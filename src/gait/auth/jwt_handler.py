"""JWT token generation and validation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from pydantic import BaseModel

from gait.common.logging_utils import get_logger

logger = get_logger(__name__)


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str  # Subject (user ID)
    exp: int  # Expiration time (Unix timestamp)
    iat: int  # Issued at (Unix timestamp)
    type: str = "access"  # Token type: access, refresh


class JWTHandler:
    """JWT token handler for creating and validating tokens."""

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """Initialize JWT handler.

        Args:
            secret_key: Secret key for signing tokens (min 32 chars for HS256)
            algorithm: JWT algorithm (default: HS256)
        """
        if len(secret_key) < 32:
            logger.warning("jwt.weak_secret", extra={"key_length": len(secret_key)})
        self.secret_key = secret_key
        self.algorithm = algorithm

    def create_access_token(
        self,
        subject: str,
        expires_in_minutes: int = 60,
        extra_claims: Optional[dict[str, Any]] = None,
    ) -> str:
        """Create a JWT access token.

        Args:
            subject: Subject (typically user ID)
            expires_in_minutes: Token expiration in minutes (default: 60)
            extra_claims: Extra claims to include in payload

        Returns:
            Encoded JWT token string

        Raises:
            ValueError: If subject is empty or expires_in_minutes is invalid
        """
        if not subject:
            raise ValueError("Subject cannot be empty")
        if expires_in_minutes <= 0:
            raise ValueError("Expiration must be positive")

        now = datetime.now(timezone.utc)
        exp = now + timedelta(minutes=expires_in_minutes)

        payload = {
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "type": "access",
        }
        if extra_claims:
            payload.update(extra_claims)

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        logger.info(
            "jwt.token_created",
            extra={"subject": subject, "expires_in_minutes": expires_in_minutes},
        )
        return token

    def create_refresh_token(
        self,
        subject: str,
        expires_in_days: int = 7,
    ) -> str:
        """Create a JWT refresh token.

        Args:
            subject: Subject (typically user ID)
            expires_in_days: Token expiration in days (default: 7)

        Returns:
            Encoded JWT token string

        Raises:
            ValueError: If subject is empty or expires_in_days is invalid
        """
        if not subject:
            raise ValueError("Subject cannot be empty")
        if expires_in_days <= 0:
            raise ValueError("Expiration must be positive")

        now = datetime.now(timezone.utc)
        exp = now + timedelta(days=expires_in_days)

        payload = {
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "type": "refresh",
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        logger.info(
            "jwt.refresh_token_created",
            extra={"subject": subject, "expires_in_days": expires_in_days},
        )
        return token

    def verify_token(self, token: str) -> TokenPayload:
        """Verify and decode a JWT token.

        Args:
            token: JWT token string

        Returns:
            TokenPayload with decoded token data

        Raises:
            jwt.ExpiredSignatureError: If token is expired
            jwt.InvalidTokenError: If token is invalid or tampered
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return TokenPayload(**payload)
        except jwt.ExpiredSignatureError:
            logger.warning("jwt.token_expired")
            raise
        except jwt.InvalidTokenError as e:
            logger.warning("jwt.invalid_token", extra={"error": str(e)})
            raise

    def verify_access_token(self, token: str) -> TokenPayload:
        """Verify a JWT access token.

        Args:
            token: JWT token string

        Returns:
            TokenPayload with decoded token data

        Raises:
            jwt.InvalidTokenError: If token is invalid or not an access token
            jwt.ExpiredSignatureError: If token is expired
        """
        payload = self.verify_token(token)
        if payload.type != "access":
            raise jwt.InvalidTokenError("Token is not an access token")
        return payload

    def verify_refresh_token(self, token: str) -> TokenPayload:
        """Verify a JWT refresh token.

        Args:
            token: JWT token string

        Returns:
            TokenPayload with decoded token data

        Raises:
            jwt.InvalidTokenError: If token is invalid or not a refresh token
            jwt.ExpiredSignatureError: If token is expired
        """
        payload = self.verify_token(token)
        if payload.type != "refresh":
            raise jwt.InvalidTokenError("Token is not a refresh token")
        return payload

    def refresh_access_token(
        self,
        refresh_token: str,
        expires_in_minutes: int = 60,
    ) -> str:
        """Create a new access token from a refresh token.

        Args:
            refresh_token: Valid refresh token
            expires_in_minutes: New access token expiration (default: 60 min)

        Returns:
            New access token

        Raises:
            jwt.InvalidTokenError: If refresh token is invalid
            jwt.ExpiredSignatureError: If refresh token is expired
        """
        payload = self.verify_refresh_token(refresh_token)
        return self.create_access_token(
            subject=payload.sub,
            expires_in_minutes=expires_in_minutes,
        )


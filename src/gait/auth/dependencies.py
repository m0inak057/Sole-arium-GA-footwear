"""FastAPI dependency injection for authentication."""
from __future__ import annotations

from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from gait.auth.api_key_manager import APIKeyValidator
from gait.auth.exceptions import (
    ExpiredTokenError,
    InvalidAPIKeyError,
    InvalidTokenError,
    MissingAuthenticationError,
)
from gait.auth.jwt_handler import JWTHandler
from gait.common.logging_utils import get_logger

logger = get_logger(__name__)

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    jwt_handler: Optional[JWTHandler] = None,
) -> str:
    """Extract and validate current user from JWT token.

    Args:
        credentials: HTTP bearer token credentials
        jwt_handler: JWT handler instance (injected)

    Returns:
        User ID (subject) from token

    Raises:
        HTTPException: If token is missing, invalid, or expired
    """
    if not credentials:
        logger.warning("auth.missing_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )

    if not jwt_handler:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT handler not configured",
        )

    try:
        payload = jwt_handler.verify_access_token(credentials.credentials)
        logger.info("auth.token_verified", extra={"user_id": payload.sub})
        return payload.sub
    except jwt.ExpiredSignatureError:
        logger.warning("auth.token_expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError as e:
        logger.warning("auth.invalid_token", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


async def validate_api_key(
    api_key: str,
    key_hash: str,
    expires_at: Optional[str] = None,
) -> bool:
    """Validate an API key.

    Args:
        api_key: Provided API key
        key_hash: Stored hash of the API key
        expires_at: ISO format expiration timestamp

    Returns:
        True if API key is valid

    Raises:
        HTTPException: If API key is invalid or expired
    """
    from datetime import datetime

    validator = APIKeyValidator()
    expires_at_dt = None
    if expires_at:
        try:
            expires_at_dt = datetime.fromisoformat(expires_at)
        except ValueError:
            logger.error("auth.invalid_expiration_format")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid expiration format",
            )

    if not validator.is_valid(key_hash, api_key, expires_at_dt):
        logger.warning("auth.invalid_api_key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    logger.info("auth.api_key_validated")
    return True


def create_jwt_handler(
    secret_key: str,
    algorithm: str = "HS256",
) -> JWTHandler:
    """Factory function to create JWT handler.

    Args:
        secret_key: Secret key for signing tokens
        algorithm: JWT algorithm

    Returns:
        Configured JWTHandler instance
    """
    return JWTHandler(secret_key=secret_key, algorithm=algorithm)


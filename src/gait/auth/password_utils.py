"""Password hashing and verification utilities."""
from __future__ import annotations

import bcrypt

from gait.common.logging_utils import get_logger

logger = get_logger(__name__)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plain text password (max 72 bytes)

    Returns:
        Hashed password (bcrypt hash as string)

    Raises:
        ValueError: If password is empty or too long
    """
    if not password:
        raise ValueError("Password cannot be empty")
    if len(password.encode()) > 72:
        raise ValueError("Password cannot exceed 72 bytes")

    password_bytes = password.encode() if isinstance(password, str) else password
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12))
    logger.info("password.hashed")
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against a bcrypt hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Bcrypt hash to verify against (string)

    Returns:
        True if password matches hash, False otherwise
    """
    try:
        password_bytes = plain_password.encode() if isinstance(plain_password, str) else plain_password
        hashed_bytes = hashed_password.encode() if isinstance(hashed_password, str) else hashed_password
        result = bcrypt.checkpw(password_bytes, hashed_bytes)
        if result:
            logger.info("password.verified")
        else:
            logger.warning("password.mismatch")
        return result
    except Exception as e:
        logger.error("password.verify_failed", extra={"error": str(e)})
        return False


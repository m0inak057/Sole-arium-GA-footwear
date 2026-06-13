"""API key management and validation."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from src.gait.common.logging_utils import get_logger

logger = get_logger(__name__)


def hash_api_key(api_key: str) -> str:
    """Hash an API key using SHA256.

    Args:
        api_key: Plain text API key

    Returns:
        SHA256 hash of the API key

    Raises:
        ValueError: If API key is empty or too short
    """
    if not api_key:
        raise ValueError("API key cannot be empty")
    if len(api_key) < 32:
        raise ValueError("API key must be at least 32 characters")

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    logger.info("api_key.hashed", extra={"key_prefix": api_key[:8]})
    return key_hash


def generate_api_key(prefix: str = "sk") -> str:
    """Generate a random API key.

    Args:
        prefix: API key prefix (default: "sk" for secret key)

    Returns:
        Generated API key (format: {prefix}_{random_32_char_hash})

    Raises:
        ValueError: If prefix is empty
    """
    if not prefix:
        raise ValueError("Prefix cannot be empty")

    import secrets
    random_bytes = secrets.token_hex(16)  # 32 hex chars = 16 bytes
    api_key = f"{prefix}_{random_bytes}"
    logger.info("api_key.generated", extra={"prefix": prefix})
    return api_key


class APIKeyValidator:
    """Validator for API keys with expiration tracking."""

    def __init__(self):
        """Initialize API key validator."""
        pass

    def is_valid(
        self,
        api_key_hash: str,
        provided_key: str,
        expires_at: datetime | None,
    ) -> bool:
        """Validate an API key against stored hash and expiration.

        Args:
            api_key_hash: Stored hash of the API key (from database)
            provided_key: Provided API key to validate
            expires_at: Expiration timestamp (None = never expires)

        Returns:
            True if key is valid and not expired, False otherwise
        """
        # Check expiration
        if expires_at:
            now = datetime.now(timezone.utc)
            if now > expires_at:
                logger.warning("api_key.expired")
                return False

        # Verify key hash using constant-time comparison
        try:
            provided_hash = hash_api_key(provided_key)
            result = _constant_time_compare(provided_hash, api_key_hash)
            if result:
                logger.info("api_key.validated")
            else:
                logger.warning("api_key.invalid")
            return result
        except ValueError:
            logger.warning("api_key.validation_error")
            return False

    def is_expiring_soon(
        self,
        expires_at: datetime | None,
        warning_days: int = 7,
    ) -> bool:
        """Check if API key is expiring within warning period.

        Args:
            expires_at: Expiration timestamp
            warning_days: Number of days to consider as "soon" (default: 7)

        Returns:
            True if key expires within warning_days, False otherwise
        """
        if not expires_at:
            return False

        now = datetime.now(timezone.utc)
        warning_threshold = now + timedelta(days=warning_days)
        return now < expires_at <= warning_threshold


def _constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings in constant time (prevent timing attacks).

    Args:
        a: First string
        b: Second string

    Returns:
        True if strings are equal, False otherwise
    """
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0

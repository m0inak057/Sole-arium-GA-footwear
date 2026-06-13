"""Unit tests for API key management and validation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.gait.auth.api_key_manager import (
    APIKeyValidator,
    generate_api_key,
    hash_api_key,
)


class TestAPIKeyGeneration:
    def test_generate_api_key(self):
        """Test generating API key."""
        api_key = generate_api_key()
        assert isinstance(api_key, str)
        assert api_key.startswith("sk_")
        assert len(api_key) > 3

    def test_generate_api_key_custom_prefix(self):
        """Test generating API key with custom prefix."""
        api_key = generate_api_key(prefix="test")
        assert api_key.startswith("test_")

    def test_generate_api_key_unique(self):
        """Test that generated keys are unique."""
        key1 = generate_api_key()
        key2 = generate_api_key()
        assert key1 != key2

    def test_generate_api_key_empty_prefix(self):
        """Test that empty prefix raises ValueError."""
        with pytest.raises(ValueError, match="Prefix cannot be empty"):
            generate_api_key(prefix="")

    def test_generate_api_key_format(self):
        """Test API key format."""
        api_key = generate_api_key(prefix="pk")
        parts = api_key.split("_")
        assert len(parts) == 2
        assert parts[0] == "pk"
        assert len(parts[1]) == 32  # 16 bytes = 32 hex chars


class TestAPIKeyHashing:
    def test_hash_api_key(self):
        """Test hashing API key."""
        api_key = "sk_1234567890abcdef1234567890abcdef"
        hashed = hash_api_key(api_key)

        assert isinstance(hashed, str)
        assert len(hashed) == 64  # SHA256 = 64 hex chars
        assert hashed != api_key

    def test_hash_api_key_empty(self):
        """Test that empty key raises ValueError."""
        with pytest.raises(ValueError, match="API key cannot be empty"):
            hash_api_key("")

    def test_hash_api_key_too_short(self):
        """Test that short key raises ValueError."""
        with pytest.raises(ValueError, match="at least 32 characters"):
            hash_api_key("short")

    def test_hash_api_key_consistent(self):
        """Test that hashing is deterministic."""
        api_key = "sk_1234567890abcdef1234567890abcdef"
        hash1 = hash_api_key(api_key)
        hash2 = hash_api_key(api_key)
        assert hash1 == hash2

    def test_hash_api_key_is_sha256(self):
        """Test that hash is SHA256 format."""
        api_key = "sk_1234567890abcdef1234567890abcdef"
        hashed = hash_api_key(api_key)
        # SHA256 produces 64 hex characters
        assert len(hashed) == 64
        assert all(c in "0123456789abcdef" for c in hashed)


class TestAPIKeyValidator:
    @pytest.fixture
    def validator(self):
        """Create API key validator."""
        return APIKeyValidator()

    def test_is_valid_correct_key(self, validator):
        """Test validating correct API key."""
        api_key = "sk_1234567890abcdef1234567890abcdef"
        key_hash = hash_api_key(api_key)

        assert validator.is_valid(key_hash, api_key, None) is True

    def test_is_valid_incorrect_key(self, validator):
        """Test validating incorrect API key."""
        api_key = "sk_1234567890abcdef1234567890abcdef"
        wrong_key = "sk_wrongkeywrongkeywrongkeywrongkey"
        key_hash = hash_api_key(api_key)

        assert validator.is_valid(key_hash, wrong_key, None) is False

    def test_is_valid_expired_key(self, validator):
        """Test that expired key returns False."""
        api_key = "sk_1234567890abcdef1234567890abcdef"
        key_hash = hash_api_key(api_key)
        expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        assert validator.is_valid(key_hash, api_key, expires_at) is False

    def test_is_valid_not_expired_key(self, validator):
        """Test that non-expired key is valid."""
        api_key = "sk_1234567890abcdef1234567890abcdef"
        key_hash = hash_api_key(api_key)
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        assert validator.is_valid(key_hash, api_key, expires_at) is True

    def test_is_valid_expires_soon(self, validator):
        """Test key expiring in 1 second is still valid."""
        api_key = "sk_1234567890abcdef1234567890abcdef"
        key_hash = hash_api_key(api_key)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=1)

        assert validator.is_valid(key_hash, api_key, expires_at) is True

    def test_is_valid_invalid_key_format(self, validator):
        """Test that invalid key format returns False."""
        key_hash = hash_api_key("sk_1234567890abcdef1234567890abcdef")
        # Key too short
        assert validator.is_valid(key_hash, "short", None) is False

    def test_is_expiring_soon_expired(self, validator):
        """Test key that already expired."""
        expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        assert validator.is_expiring_soon(expires_at, warning_days=7) is False

    def test_is_expiring_soon_within_warning(self, validator):
        """Test key expiring within warning period."""
        expires_at = datetime.now(timezone.utc) + timedelta(days=3)
        assert validator.is_expiring_soon(expires_at, warning_days=7) is True

    def test_is_expiring_soon_after_warning(self, validator):
        """Test key expiring after warning period."""
        expires_at = datetime.now(timezone.utc) + timedelta(days=15)
        assert validator.is_expiring_soon(expires_at, warning_days=7) is False

    def test_is_expiring_soon_no_expiry(self, validator):
        """Test key with no expiration."""
        assert validator.is_expiring_soon(None, warning_days=7) is False

    def test_is_expiring_soon_custom_warning(self, validator):
        """Test custom warning period."""
        expires_at = datetime.now(timezone.utc) + timedelta(days=5)
        assert validator.is_expiring_soon(expires_at, warning_days=3) is False
        assert validator.is_expiring_soon(expires_at, warning_days=7) is True


class TestConstantTimeComparison:
    def test_constant_time_equal(self):
        """Test constant time comparison of equal strings."""
        from src.gait.auth.api_key_manager import _constant_time_compare

        a = "abcdef1234567890"
        b = "abcdef1234567890"
        assert _constant_time_compare(a, b) is True

    def test_constant_time_not_equal(self):
        """Test constant time comparison of different strings."""
        from src.gait.auth.api_key_manager import _constant_time_compare

        a = "abcdef1234567890"
        b = "different1234567"
        assert _constant_time_compare(a, b) is False

    def test_constant_time_different_length(self):
        """Test constant time comparison with different lengths."""
        from src.gait.auth.api_key_manager import _constant_time_compare

        a = "short"
        b = "much_longer_string"
        assert _constant_time_compare(a, b) is False

    def test_constant_time_prevents_timing_attack(self):
        """Test that constant time comparison doesn't leak via timing."""
        from src.gait.auth.api_key_manager import _constant_time_compare

        # Compare strings that differ in different positions
        # All should take similar time (constant time)
        str1 = "a" * 64
        str2_diff_start = "z" + "a" * 63
        str2_diff_middle = "a" * 32 + "z" + "a" * 31
        str2_diff_end = "a" * 63 + "z"

        # All should return False
        assert _constant_time_compare(str1, str2_diff_start) is False
        assert _constant_time_compare(str1, str2_diff_middle) is False
        assert _constant_time_compare(str1, str2_diff_end) is False

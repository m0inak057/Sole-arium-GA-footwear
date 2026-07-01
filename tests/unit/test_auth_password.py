"""Unit tests for password hashing and verification."""
from __future__ import annotations

import pytest

from gait.auth.password_utils import hash_password, verify_password


class TestPasswordHashing:
    def test_hash_password(self):
        """Test hashing a password."""
        password = "my-secure-password-123"
        hashed = hash_password(password)

        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != password  # Hash should not equal original

    def test_hash_password_empty(self):
        """Test that empty password raises ValueError."""
        with pytest.raises(ValueError, match="Password cannot be empty"):
            hash_password("")

    def test_hash_password_deterministic_salt(self):
        """Test that same password produces different hashes (due to random salt)."""
        password = "test-password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Different hashes due to salt
        assert hash1 != hash2
        # But both verify correctly
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_hash_password_long(self):
        """Test hashing a long password (bcrypt max 72 bytes)."""
        password = "a" * 71  # Bcrypt limit is 72 bytes
        hashed = hash_password(password)
        assert verify_password(password, hashed)

    def test_hash_password_special_chars(self):
        """Test hashing password with special characters."""
        password = "p@ssw0rd!#$%^&*()"
        hashed = hash_password(password)
        assert verify_password(password, hashed)


class TestPasswordVerification:
    def test_verify_password_correct(self):
        """Test verifying correct password."""
        password = "correct-password"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test verifying incorrect password."""
        password = "correct-password"
        wrong_password = "wrong-password"
        hashed = hash_password(password)
        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_case_sensitive(self):
        """Test that password verification is case sensitive."""
        password = "MyPassword"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True
        assert verify_password(password.lower(), hashed) is False

    def test_verify_password_leading_trailing_space(self):
        """Test that leading/trailing spaces matter."""
        password = "password"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True
        assert verify_password(" password", hashed) is False
        assert verify_password("password ", hashed) is False

    def test_verify_password_invalid_hash(self):
        """Test that invalid hash format returns False."""
        password = "test-password"
        invalid_hash = "not-a-valid-bcrypt-hash"
        assert verify_password(password, invalid_hash) is False

    def test_verify_password_empty_password(self):
        """Test verifying with empty password."""
        hashed = hash_password("test")
        assert verify_password("", hashed) is False

    def test_verify_password_empty_hash(self):
        """Test verifying against empty hash."""
        password = "test"
        assert verify_password(password, "") is False

    def test_verify_password_unicode(self):
        """Test password with unicode characters."""
        password = "p@sswörd™"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True
        assert verify_password("p@ssword", hashed) is False  # Different without unicode


class TestPasswordSecurity:
    def test_hash_is_bcrypt(self):
        """Test that hash is bcrypt format."""
        password = "test-password"
        hashed = hash_password(password)
        # Bcrypt hashes start with $2a$, $2b$, $2x$, or $2y$
        assert hashed.startswith(("$2a$", "$2b$", "$2x$", "$2y$"))

    def test_hash_includes_cost(self):
        """Test that bcrypt hash includes cost factor."""
        password = "test-password"
        hashed = hash_password(password)
        # Bcrypt cost should be between $2b$10$ and $2b$12$
        assert "$10$" in hashed or "$11$" in hashed or "$12$" in hashed

    def test_different_passwords_different_hashes(self):
        """Test that different passwords produce different hashes."""
        password1 = "password1"
        password2 = "password2"
        hash1 = hash_password(password1)
        hash2 = hash_password(password2)

        assert hash1 != hash2
        assert not verify_password(password2, hash1)
        assert not verify_password(password1, hash2)


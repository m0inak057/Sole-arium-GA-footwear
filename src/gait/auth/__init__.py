"""Authentication module (JWT, API keys, passwords)."""
from src.gait.auth.api_key_manager import APIKeyValidator, generate_api_key, hash_api_key
from src.gait.auth.dependencies import (
    create_jwt_handler,
    get_current_user,
    validate_api_key,
)
from src.gait.auth.exceptions import (
    AuthenticationError,
    ExpiredTokenError,
    InsufficientPermissionsError,
    InvalidAPIKeyError,
    InvalidCredentialsError,
    InvalidTokenError,
    MissingAuthenticationError,
)
from src.gait.auth.jwt_handler import JWTHandler, TokenPayload
from src.gait.auth.password_utils import hash_password, verify_password

__all__ = [
    "JWTHandler",
    "TokenPayload",
    "hash_password",
    "verify_password",
    "hash_api_key",
    "generate_api_key",
    "APIKeyValidator",
    "create_jwt_handler",
    "get_current_user",
    "validate_api_key",
    "AuthenticationError",
    "InvalidCredentialsError",
    "InvalidTokenError",
    "ExpiredTokenError",
    "InvalidAPIKeyError",
    "MissingAuthenticationError",
    "InsufficientPermissionsError",
]

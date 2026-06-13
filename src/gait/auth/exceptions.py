"""Authentication-related exceptions."""


class AuthenticationError(Exception):
    """Base exception for authentication errors."""
    pass


class InvalidCredentialsError(AuthenticationError):
    """Raised when credentials (username/password) are invalid."""
    pass


class InvalidTokenError(AuthenticationError):
    """Raised when JWT token is invalid or tampered."""
    pass


class ExpiredTokenError(AuthenticationError):
    """Raised when JWT token has expired."""
    pass


class InvalidAPIKeyError(AuthenticationError):
    """Raised when API key is invalid or expired."""
    pass


class MissingAuthenticationError(AuthenticationError):
    """Raised when authentication is missing or incomplete."""
    pass


class InsufficientPermissionsError(AuthenticationError):
    """Raised when user lacks required permissions."""
    pass

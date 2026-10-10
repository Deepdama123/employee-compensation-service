"""Application errors, each mapped to one HTTP status code.

Lower layers raise these; the HTTP layer turns them into JSON responses.
Anything that is not an ApiError becomes a generic 500 so internal
details (SQL text, server names, stack traces) never reach the client.
"""


class ApiError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(ApiError):
    status_code = 400
    code = "validation_error"


class NotFoundError(ApiError):
    status_code = 404
    code = "not_found"


class ConflictError(ApiError):
    status_code = 409
    code = "conflict"


class ServiceUnavailableError(ApiError):
    status_code = 503
    code = "service_unavailable"


class ConfigurationError(ApiError):
    """Missing/invalid app settings. Logged in full, returned as a plain 500."""

    status_code = 500
    code = "internal_error"

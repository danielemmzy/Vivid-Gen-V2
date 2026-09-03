"""Typed application exceptions. Routers never build ad-hoc HTTPException
dicts for domain errors — they raise one of these, and a single handler in
main.py maps it to an HTTP response. This keeps error shape consistent and
means we can log/alert on them centrally by exception type."""
from typing import Any


class VividGenError(Exception):
    """Base class for all domain errors. `code` is a stable machine-readable
    identifier the frontend can switch on; `http_status` picks the response."""
    http_status: int = 400
    code: str = "ERROR"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.details}


class InsufficientCreditsError(VividGenError):
    http_status = 402
    code = "INSUFFICIENT_CREDITS"


class ModelNotFoundError(VividGenError):
    http_status = 400
    code = "MODEL_NOT_FOUND"


class UnsupportedModelForTypeError(VividGenError):
    http_status = 400
    code = "UNSUPPORTED_MODEL_FOR_TYPE"


class InvalidGenerationParamsError(VividGenError):
    http_status = 400
    code = "INVALID_GENERATION_PARAMS"


class ProviderSubmissionError(VividGenError):
    http_status = 502
    code = "PROVIDER_SUBMISSION_FAILED"


class ProviderTimeoutError(VividGenError):
    http_status = 504
    code = "PROVIDER_TIMEOUT"


class GenerationNotFoundError(VividGenError):
    http_status = 404
    code = "GENERATION_NOT_FOUND"


class ContentModerationError(VividGenError):
    http_status = 422
    code = "CONTENT_REJECTED"


class RateLimitExceededError(VividGenError):
    http_status = 429
    code = "RATE_LIMIT_EXCEEDED"


class ConcurrencyLimitExceededError(VividGenError):
    http_status = 429
    code = "TOO_MANY_ACTIVE_GENERATIONS"


class UnauthorizedError(VividGenError):
    http_status = 401
    code = "UNAUTHORIZED"


class ForbiddenError(VividGenError):
    http_status = 403
    code = "FORBIDDEN"


class GenerationsDisabledError(VividGenError):
    http_status = 503
    code = "GENERATIONS_DISABLED"


class ProjectNotFoundError(VividGenError):
    http_status = 404
    code = "PROJECT_NOT_FOUND"


class CharacterNotFoundError(VividGenError):
    http_status = 404
    code = "CHARACTER_NOT_FOUND"


class ProjectLimitExceededError(VividGenError):
    http_status = 400
    code = "PROJECT_LIMIT_EXCEEDED"

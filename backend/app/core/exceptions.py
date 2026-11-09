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


class PlanValidationError(VividGenError):
    """Raised by orchestration/plan_validator.py. `details["errors"]` is the
    full list of validation problems, not just the first — the frontend
    shows all of them at once rather than making the user fix-and-resubmit
    one at a time."""
    http_status = 422
    code = "PLAN_VALIDATION_FAILED"


class RenderJobNotFoundError(VividGenError):
    http_status = 404
    code = "RENDER_JOB_NOT_FOUND"


class ExportNotFoundError(VividGenError):
    http_status = 404
    code = "EXPORT_NOT_FOUND"


class ProjectNotRenderableError(VividGenError):
    """Raised by services/export/service.py when an export is requested
    against a project that has no completed master yet."""
    http_status = 400
    code = "PROJECT_NOT_RENDERABLE"


class UnsupportedUploadTypeError(VividGenError):
    http_status = 400
    code = "UNSUPPORTED_UPLOAD_TYPE"


class GenerationNotCancellableError(VividGenError):
    http_status = 400
    code = "GENERATION_NOT_CANCELLABLE"


class ProjectNotCancellableError(VividGenError):
    http_status = 400
    code = "PROJECT_NOT_CANCELLABLE"


# --- gap-closure (0007): Production domain ---

class ProductionNotFoundError(VividGenError):
    http_status = 404
    code = "PRODUCTION_NOT_FOUND"


class ProductionNotCancellableError(VividGenError):
    http_status = 400
    code = "PRODUCTION_NOT_CANCELLABLE"


class InvalidDagError(VividGenError):
    """Raised by orchestration/dag.py's validation pass — a cycle, a
    dangling edge (references a task not in this production), or a
    duplicate edge. A production is never allowed to start executing
    with a DAG that fails this check; `details["errors"]` carries every
    problem found, not just the first."""
    http_status = 422
    code = "INVALID_PRODUCTION_DAG"


class InsufficientProductionBudgetError(VividGenError):
    """Raised by services/production/budget_service.py when a
    production's estimated cost exceeds the user's available balance at
    reservation time."""
    http_status = 402
    code = "INSUFFICIENT_PRODUCTION_BUDGET"


class ProductionBudgetNotFoundError(VividGenError):
    http_status = 404
    code = "PRODUCTION_BUDGET_NOT_FOUND"


# --- Round 4: Asset/Model/Audio routers, Product domain ---

class ProductNotFoundError(VividGenError):
    http_status = 404
    code = "PRODUCT_NOT_FOUND"


class ProviderNotConfiguredError(VividGenError):
    """Raised (or, more often, just returned as an explicit
    ProviderAvailabilityStatus.NOT_CONFIGURED result — routers generally
    prefer that to raising, so a missing stock/music provider degrades
    gracefully rather than failing a whole scene) when a provider needs
    credentials that aren't present. Distinct from a runtime provider
    failure — see core/constants.py::ProviderAvailabilityStatus."""
    http_status = 424
    code = "PROVIDER_NOT_CONFIGURED"


class AssetResolutionError(VividGenError):
    """Raised by orchestration/asset_router.py when no candidate asset
    could be resolved for a scene's requirement through any source."""
    http_status = 422
    code = "ASSET_RESOLUTION_FAILED"


class CaptionTrackNotFoundError(VividGenError):
    http_status = 404
    code = "CAPTION_TRACK_NOT_FOUND"

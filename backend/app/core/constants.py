"""Enumerated constants shared across the app. Centralized so a typo in a
status string can't silently create a new, unhandled state."""
from enum import StrEnum


class GenerationStatus(StrEnum):
    QUEUED = "queued"
    RESERVING_CREDITS = "reserving_credits"
    PROCESSING = "processing"           # submitted to provider, awaiting webhook
    POSTPROCESSING = "postprocessing"   # webhook received, worker finalizing media
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"             # user-initiated; refunds like FAILED but not a provider/system error

    @property
    def is_terminal(self) -> bool:
        return self in {
            GenerationStatus.COMPLETED, GenerationStatus.FAILED,
            GenerationStatus.REFUNDED, GenerationStatus.CANCELLED,
        }


class GenerationType(StrEnum):
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    AVATAR = "avatar"                # talking photo / lip-sync from audio
    VIDEO_TRANSLATION = "video_translation"
    AUDIO_REPLACE = "audio_replace"
    MOVIE_SHOT = "movie_shot"        # a single shot generated inside a Project


class PricingUnit(StrEnum):
    SECOND = "second"
    MINUTE = "minute"
    IMAGE = "image"
    MEGAPIXEL = "megapixel"
    FLAT = "flat"


class CreditTransactionType(StrEnum):
    GRANT = "GRANT"                       # free tier / signup bonus
    PURCHASE = "PURCHASE"                 # Polar checkout
    SUBSCRIPTION_RENEWAL = "SUBSCRIPTION_RENEWAL"
    GENERATION_RESERVATION = "GENERATION_RESERVATION"
    GENERATION_CHARGE = "GENERATION_CHARGE"
    GENERATION_REFUND = "GENERATION_REFUND"
    ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    # --- V2: AI Director states, added this phase. A project sits here
    # between POST /plan and POST /approve-plan; existing V1 code (movie
    # service, media job) never sets or checks these, so this is additive.
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    CANCELLED = "cancelled"
    GENERATING = "generating"
    ASSEMBLING = "assembling"
    READY = "ready"
    FAILED = "failed"


class ShotStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ModerationVerdict(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    FLAG_FOR_REVIEW = "flag_for_review"


class RenderJobStatus(StrEnum):
    """gap-closure: real render observability. See models/render_job.py."""
    QUEUED = "queued"
    PREPARING = "preparing"     # building the RenderManifest (voiceover/captions/music synthesis)
    RENDERING = "rendering"     # renderer.render() running ffmpeg against the manifest
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {RenderJobStatus.COMPLETED, RenderJobStatus.FAILED}


class ExportStatus(StrEnum):
    """gap-closure: Content Factory variant/export records. See models/export.py."""
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProviderErrorClass(StrEnum):
    """gap-closure: error taxonomy so a provider failure can be classified
    once and consistently drive retry/fallback vs. immediate-refund
    behavior — see orchestration/provider_errors.py."""
    TRANSIENT = "transient"   # timeout, 5xx, rate-limited, capacity/GPU-unavailable — worth retrying
    PERMANENT = "permanent"   # invalid input, unsupported capability, policy-rejected — retrying wastes credits/time


class ProductionTaskType(StrEnum):
    """gap-closure (0007): each of these is now a real DAG node — see
    orchestration/dag.py for how they're wired together with actual
    dependency edges (ProductionTaskDependency), not just listed flat."""
    SCENE = "scene"
    VOICE = "voice"
    CAPTIONS = "captions"
    MUSIC = "music"
    BRANDING = "branding"
    RENDER = "render"


class ProductionTaskStatus(StrEnum):
    """gap-closure (0007): BLOCKED/READY are new — see
    orchestration/dag.py's docstring for the scheduler algorithm these
    drive. A task starts BLOCKED if it has any upstream dependency, or
    READY if it has none (a root task). BLOCKED -> READY happens only
    when every upstream dependency reaches a "satisfied" terminal state
    (COMPLETED or SKIPPED — see `is_satisfied` below), evaluated
    atomically by orchestration/scheduler.py whenever a task completes."""
    BLOCKED = "blocked"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # e.g. a scene whose visual_type has no provider — see executor.py

    @property
    def is_terminal(self) -> bool:
        return self in {ProductionTaskStatus.COMPLETED, ProductionTaskStatus.FAILED, ProductionTaskStatus.SKIPPED}

    @property
    def is_satisfied(self) -> bool:
        """Whether a downstream task may count this as satisfied when
        evaluating its own readiness. FAILED is deliberately NOT
        satisfied — see orchestration/scheduler.py's failure-propagation
        logic, which fails dependents rather than leaving them BLOCKED
        forever."""
        return self in {ProductionTaskStatus.COMPLETED, ProductionTaskStatus.SKIPPED}


class ProductionStatus(StrEnum):
    """gap-closure (0007): Production — previously a production run had
    no object of its own; this was implicitly Project.status. See
    models/production.py."""
    DRAFT = "draft"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {ProductionStatus.COMPLETED, ProductionStatus.FAILED, ProductionStatus.CANCELLED}


class ProductionPlanStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    SUPERSEDED = "superseded"  # an edited re-plan replaced this version


class ProductionBudgetStatus(StrEnum):
    """gap-closure (0007): ProductionBudget lifecycle — estimate -> reserve
    -> execute -> reconcile -> refund/release. See
    services/production/budget_service.py."""
    ESTIMATED = "estimated"
    RESERVED = "reserved"
    EXECUTING = "executing"
    RECONCILED = "reconciled"
    REFUNDED = "refunded"
    FAILED = "failed"


class ProductionBudgetLedgerType(StrEnum):
    ESTIMATE = "estimate"
    RESERVE = "reserve"
    CHARGE = "charge"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"
    RELEASE = "release"


class GenerationAttemptStatus(StrEnum):
    """gap-closure (0007): GenerationAttempt — additive per-attempt audit
    history alongside the existing Generation.retry_count/
    attempted_model_ids bookkeeping (that stays as the authoritative
    counter for retry-loop control; GenerationAttempt is the queryable
    record of what happened on each individual try). See
    services/generation/service.py."""
    SUBMITTED = "submitted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProviderAvailabilityStatus(StrEnum):
    """Round 4 (confirmed additional requirement): a missing API key and
    a failing API call are different conditions, and every router
    (Asset/Model/Audio) must be able to tell them apart rather than
    collapsing both into one boolean "unavailable". See
    models/provider_health.py and orchestration/provider_health.py."""
    AVAILABLE = "available"
    NOT_CONFIGURED = "not_configured"          # no API key/credential present — a deployment/config gap, not a runtime failure
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"  # configured, but recent calls are erroring (5xx/timeout pattern)
    RATE_LIMITED = "rate_limited"               # configured, provider is actively throttling
    FAILED = "failed"                           # configured, but every recent attempt failed — treat as down until it recovers

    @property
    def is_routable(self) -> bool:
        """Whether a router should even consider this provider/model as
        a candidate at all — NOT_CONFIGURED and FAILED are hard
        exclusions; TEMPORARILY_UNAVAILABLE/RATE_LIMITED are soft
        (heavily penalized in scoring, but usable as a last resort if no
        other candidate exists) — see orchestration/model_router.py."""
        return self != ProviderAvailabilityStatus.NOT_CONFIGURED


class AssetSourceType(StrEnum):
    """Round 4: what the Asset Router actually chose for a scene — see
    orchestration/asset_router.py. Distinct from Asset.source_provider
    (which vendor/system produced the file); this is the ROUTING
    decision category."""
    USER_ASSET = "user_asset"
    CHARACTER_REFERENCE = "character_reference"
    PRODUCT_REFERENCE = "product_reference"
    BRAND_ASSET = "brand_asset"
    EXISTING_GENERATED = "existing_generated"
    STOCK_SEARCH = "stock_search"
    STOCK_URL = "stock_url"
    GENERATED = "generated"
    TEXT_GRAPHIC = "text_graphic"
    SCENE_REFERENCE = "scene_reference"  # round 4 decision #5 — an earlier scene's actual output


REDIS_KEY_PREFIX = "vividgen"
IDEMPOTENCY_HEADER = "Idempotency-Key"
CORRELATION_ID_HEADER = "X-Correlation-ID"
REQUEST_ID_HEADER = "X-Request-ID"

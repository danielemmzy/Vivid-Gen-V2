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

    @property
    def is_terminal(self) -> bool:
        return self in {GenerationStatus.COMPLETED, GenerationStatus.FAILED, GenerationStatus.REFUNDED}


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


REDIS_KEY_PREFIX = "vividgen"
IDEMPOTENCY_HEADER = "Idempotency-Key"
CORRELATION_ID_HEADER = "X-Correlation-ID"
REQUEST_ID_HEADER = "X-Request-ID"

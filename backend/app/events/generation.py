"""Domain events for the generation lifecycle. Kept as plain dataclasses,
dispatched via events/bus.py. This is intentionally lightweight (no message
broker) — it's a decoupling seam inside one process, not a distributed
event system. If Vivid Gen later needs cross-service events, replace the
bus's in-process dispatch with a real broker (SNS/SQS, Redis Streams)
without changing any event definition or any caller of `dispatch()`."""
from dataclasses import dataclass

from app.events.base import DomainEvent


@dataclass(frozen=True)
class GenerationSubmitted(DomainEvent):
    generation_id: str
    user_id: str
    generation_type: str
    model_id: str
    credits_reserved: int


@dataclass(frozen=True)
class GenerationSubmissionFailed(DomainEvent):
    generation_id: str
    user_id: str
    error_code: str
    credits_refunded: int


@dataclass(frozen=True)
class GenerationCompleted(DomainEvent):
    generation_id: str
    user_id: str
    credits_charged: int


@dataclass(frozen=True)
class GenerationFailed(DomainEvent):
    generation_id: str
    user_id: str
    error_code: str
    credits_refunded: int

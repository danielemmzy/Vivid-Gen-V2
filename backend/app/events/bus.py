"""Minimal synchronous in-process event bus. Handlers registered here run
inline, in-order, within the caller's context — they must be fast and
must not raise (a handler exception must never break the generation
request that triggered it). Use this for logging, metrics, and enqueueing
follow-up jobs; anything slower belongs in a job, dispatched from a
handler, not run directly on the event."""
from collections import defaultdict
from collections.abc import Callable

from app.core.logging import get_logger
from app.events.base import DomainEvent

logger = get_logger(__name__)

_handlers: dict[type, list[Callable[[DomainEvent], None]]] = defaultdict(list)


def subscribe(event_type: type, handler: Callable[[DomainEvent], None]) -> None:
    _handlers[event_type].append(handler)


def dispatch(event: DomainEvent) -> None:
    for handler in _handlers.get(type(event), []):
        try:
            handler(event)
        except Exception as exc:  # noqa: BLE001 - a handler must never break the caller
            logger.error("event_handler_error", event=type(event).__name__, error=str(exc))

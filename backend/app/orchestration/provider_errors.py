"""gap-closure: error taxonomy.

Before this, every provider failure — a malformed prompt, a 5xx, a rate
limit, a GPU-capacity error — was handled identically: refund and stop
(see webhooks/fal.py and services/generation/service.py's except blocks
in the pre-audit code). `model_router.select_with_fallback` existed to
build a fallback chain but was never called from anywhere, because
nothing decided *when* falling back was actually appropriate.

This module is that decision. It doesn't try to be a complete provider
error catalogue — fal.ai (and any future provider) doesn't publish one
machine-readable enum we can rely on — so it works of a payload/exception
whatever text is available and matches known-transient signals. Anything
that doesn't match a known-transient signal is treated as PERMANENT. That
default is deliberate: retrying an error we can't positively identify as
transient risks burning provider spend and the user's reserved credits on
repeats of a failure that will never succeed (e.g. an unsupported
resolution) — false negatives (calling a transient error permanent) cost
one avoidable refund; false positives (retrying a permanent error) cost
real provider money on every retry. Bias toward the cheaper mistake.
"""
import re

from app.core.constants import ProviderErrorClass

_TRANSIENT_PATTERNS = [
    r"\btimeout\b", r"\btimed out\b",
    r"\brate.?limit", r"\btoo many requests\b", r"\b429\b",
    r"\b5\d\d\b",  # any 5xx status code mentioned in the message
    r"\bcapacity\b", r"\bgpu unavailable\b", r"\bno available worker",
    r"\bservice unavailable\b", r"\bconnection reset\b", r"\bconnection.?error\b",
    r"\bnetwork\b", r"\btemporarily unavailable\b", r"\bqueue full\b",
    r"\boverloaded\b", r"\bbusy\b",
]
_TRANSIENT_RE = re.compile("|".join(_TRANSIENT_PATTERNS), re.IGNORECASE)

_PERMANENT_PATTERNS = [
    r"\binvalid\b", r"\bunsupported\b", r"\bpolicy\b", r"\bmoderat",
    r"\bnsfw\b", r"\bcontent.?rejected\b", r"\b400\b", r"\b401\b", r"\b403\b",
    r"\bnot found\b", r"\b404\b", r"\bmalformed\b", r"\btoo (long|large)\b",
    r"\bunauthorized\b", r"\bforbidden\b",
]
_PERMANENT_RE = re.compile("|".join(_PERMANENT_PATTERNS), re.IGNORECASE)


def classify_error(message: str | None, *, status_code: int | None = None) -> ProviderErrorClass:
    """Classify a provider failure from whatever text/status we have.
    Permanent signals are checked first: a message that contains both an
    "invalid" and a "500" (some providers wrap a 400-shaped validation
    error inside a 500 envelope) should not be retried, since retrying it
    will just fail identically. Falls back to PERMANENT if nothing matches
    (see module docstring for why that's the safer default)."""
    text = message or ""
    if status_code is not None:
        if 500 <= status_code < 600:
            return ProviderErrorClass.TRANSIENT
        if 400 <= status_code < 500 and status_code != 429:
            return ProviderErrorClass.PERMANENT

    if _PERMANENT_RE.search(text):
        return ProviderErrorClass.PERMANENT
    if _TRANSIENT_RE.search(text):
        return ProviderErrorClass.TRANSIENT
    return ProviderErrorClass.PERMANENT


def classify_exception(exc: Exception) -> ProviderErrorClass:
    """Classify a synchronous submission-time exception (e.g. the fal SDK
    raising on a connection failure before a request_id even exists)."""
    status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    return classify_error(str(exc), status_code=status_code if isinstance(status_code, int) else None)

"""Round 4, decision #3 (confirmed): ProviderHealth read/write.

Called from exactly three places: `services/generation/service.py`
(after each GenerationAttempt resolves), `orchestration/asset_router.py`
(after a stock search call), and `orchestration/audio_router.py` (after
a music search call) — every place this codebase actually makes an
external provider call whose success/failure is worth remembering.

Status transition rule (deterministic, documented, not tuned against
live traffic since none was available to tune against in this session):
a SUCCESS always resets status to AVAILABLE immediately (a provider that
just worked is available, full stop — no time-windowed decay needed to
express "it recovered"). A FAILURE escalates based on the all-time
ratio: <3 total attempts or ratio < 0.5 -> TEMPORARILY_UNAVAILABLE (soft
warning, still usable as a last resort); ratio >= 0.5 with >=3 attempts
-> FAILED (excluded except as an explicit last resort — see
model_router.py). A 429/rate-limit response is recorded as RATE_LIMITED
regardless of ratio, since that's a specific, different signal (the
provider IS working, just asking to slow down).
"""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ProviderAvailabilityStatus
from app.models.provider_health import ProviderHealth


async def _get_or_create(session: AsyncSession, *, provider: str, model_id: str | None, capability: str | None) -> ProviderHealth:
    row = (
        await session.execute(
            select(ProviderHealth).where(
                ProviderHealth.provider == provider, ProviderHealth.model_id == model_id, ProviderHealth.capability == capability,
            )
        )
    ).scalar_one_or_none()
    if row:
        return row
    row = ProviderHealth(id="phealth_" + uuid4().hex, provider=provider, model_id=model_id, capability=capability)
    session.add(row)
    await session.flush()
    return row


async def get_status(session: AsyncSession, *, provider: str, model_id: str | None = None, capability: str | None = None) -> ProviderAvailabilityStatus:
    """Returns AVAILABLE for a provider/model with no recorded history
    yet — a brand-new candidate is not penalized for having no track
    record."""
    row = (
        await session.execute(
            select(ProviderHealth).where(
                ProviderHealth.provider == provider, ProviderHealth.model_id == model_id, ProviderHealth.capability == capability,
            )
        )
    ).scalar_one_or_none()
    if not row:
        return ProviderAvailabilityStatus.AVAILABLE
    return ProviderAvailabilityStatus(row.status)


async def get_health(session: AsyncSession, *, provider: str, model_id: str | None = None, capability: str | None = None) -> ProviderHealth | None:
    return (
        await session.execute(
            select(ProviderHealth).where(
                ProviderHealth.provider == provider, ProviderHealth.model_id == model_id, ProviderHealth.capability == capability,
            )
        )
    ).scalar_one_or_none()


async def record_success(session: AsyncSession, *, provider: str, model_id: str | None = None, capability: str | None = None, latency_ms: float | None = None) -> None:
    row = await _get_or_create(session, provider=provider, model_id=model_id, capability=capability)
    row.success_count += 1
    row.last_success_at = datetime.now(timezone.utc)
    row.status = ProviderAvailabilityStatus.AVAILABLE  # a fresh success always clears any degraded state
    if latency_ms is not None:
        # Simple running average — good enough for routing preference,
        # not meant to be a precise percentile metric.
        prior = float(row.avg_latency_ms) if row.avg_latency_ms is not None else latency_ms
        total = row.success_count + row.failure_count
        row.avg_latency_ms = prior + (latency_ms - prior) / max(total, 1)
    await session.commit()


async def record_failure(session: AsyncSession, *, provider: str, model_id: str | None = None, capability: str | None = None, timeout: bool = False, rate_limited: bool = False) -> None:
    row = await _get_or_create(session, provider=provider, model_id=model_id, capability=capability)
    row.failure_count += 1
    if timeout:
        row.timeout_count += 1
    row.last_failure_at = datetime.now(timezone.utc)

    if rate_limited:
        row.status = ProviderAvailabilityStatus.RATE_LIMITED
    else:
        total = row.success_count + row.failure_count
        ratio = row.failure_count / total if total else 1.0
        row.status = ProviderAvailabilityStatus.FAILED if (total >= 3 and ratio >= 0.5) else ProviderAvailabilityStatus.TEMPORARILY_UNAVAILABLE
    await session.commit()

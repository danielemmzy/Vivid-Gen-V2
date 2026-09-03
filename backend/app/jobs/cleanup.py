"""Scheduled housekeeping jobs — expired presigned-upload orphans and old
webhook_event rows. Run by scheduler/tasks.py, not by user-triggered
requests."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.core.database import system_session
from app.core.logging import get_logger
from app.models.webhook_event import WebhookEvent

logger = get_logger(__name__)


async def purge_old_webhook_events(retention_days: int = 30) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    async with system_session() as session:
        result = await session.execute(delete(WebhookEvent).where(WebhookEvent.received_at < cutoff))
        await session.commit()
        return result.rowcount or 0

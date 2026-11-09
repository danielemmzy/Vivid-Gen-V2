"""Extremely thin — this is exactly what the architecture plan calls for:
verify -> delegate -> return fast. All state logic lives in
app/webhooks/fal.py / app/webhooks/modal.py."""
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.dependencies import system_db_session
from app.services.providers.fal.webhook import verify_fal_webhook
from app.services.providers.modal.webhook import verify_modal_webhook
from app.webhooks.fal import handle_fal_webhook
from app.webhooks.modal import handle_modal_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/fal")
async def fal_webhook(
    request: Request,
    session: AsyncSession = Depends(system_db_session),
    x_fal_webhook_request_id: str | None = Header(None),
    x_fal_webhook_user_id: str | None = Header(None),
    x_fal_webhook_timestamp: str | None = Header(None),
    x_fal_webhook_signature: str | None = Header(None),
):
    body = await request.body()
    if not await verify_fal_webhook(x_fal_webhook_request_id, x_fal_webhook_user_id, x_fal_webhook_timestamp, x_fal_webhook_signature, body):
        raise HTTPException(401, "Invalid fal webhook signature")
    payload = await request.json()
    return await handle_fal_webhook(session, payload)


@router.post("/modal")
async def modal_webhook(
    request: Request,
    session: AsyncSession = Depends(system_db_session),
    x_modal_timestamp: str | None = Header(None),
    x_modal_signature: str | None = Header(None),
):
    body = await request.body()
    if not verify_modal_webhook(x_modal_timestamp, x_modal_signature, body):
        raise HTTPException(401, "Invalid Modal webhook signature")
    payload = await request.json()
    return await handle_modal_webhook(session, payload)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.dependencies import current_user_id, db_session
from app.services.credits.service import CreditService
from app.core.config import settings

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get("/balance")
async def balance(user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    return {"credits": await CreditService(session).balance(user_id), "credit_usd_value": settings.credit_usd_value}


@router.get("/transactions")
async def transactions(user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    return {"transactions": await CreditService(session).transactions(user_id)}


@router.get("/packages")
async def credit_packages(_user_id: str = Depends(current_user_id)):
    packages = [
        {"key": "small", "title": "Starter", "product_id": settings.polar_small_credit_product_id,
         "credits": settings.polar_small_credit_amount, "price_usd": settings.polar_small_credit_price_usd},
        {"key": "medium", "title": "Creator", "product_id": settings.polar_medium_credit_product_id,
         "credits": settings.polar_medium_credit_amount, "price_usd": settings.polar_medium_credit_price_usd},
        {"key": "large", "title": "Studio", "product_id": settings.polar_large_credit_product_id,
         "credits": settings.polar_large_credit_amount, "price_usd": settings.polar_large_credit_price_usd},
    ]
    configured = all(item["product_id"] and item["credits"] > 0 for item in packages)
    return {"configured": configured, "packages": packages,
            "message": None if configured else "Credit packs are disabled until all three Polar product IDs and credit amounts are configured on the backend."}


class PurchaseGrantRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=150)
    product_id: str = Field(min_length=1, max_length=191)


@router.post("/purchase")
async def grant_paid_credit_pack(body: PurchaseGrantRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """Internal Next.js Polar onOrderPaid relay. Product IDs are allowlisted server-side;
    order IDs are unique in the append-only ledger so webhook retries never double-credit."""
    packages = {
        settings.polar_small_credit_product_id: (settings.polar_small_credit_amount, "Small credit pack"),
        settings.polar_medium_credit_product_id: (settings.polar_medium_credit_amount, "Medium credit pack"),
        settings.polar_large_credit_product_id: (settings.polar_large_credit_amount, "Large credit pack"),
    }
    packages.pop("", None)
    package = packages.get(body.product_id)
    if not package:
        raise HTTPException(422, "This Polar product is not configured as a credit pack in the backend.")
    amount, label = package
    if amount <= 0:
        raise HTTPException(503, "The configured credit pack has an invalid credit amount.")
    from app.monitoring.metrics import credit_purchase_total
    balance, newly_granted = await CreditService(session).grant_purchase_once(
        user_id, amount, f"Polar {label} (order {body.order_id})", f"polar-order:{body.order_id}",
    )
    await session.commit()
    credit_purchase_total.labels("granted" if newly_granted else "duplicate").inc()
    return {"credits_added": amount if newly_granted else 0, "balance": balance, "duplicate_webhook": not newly_granted}

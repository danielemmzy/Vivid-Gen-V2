from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

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

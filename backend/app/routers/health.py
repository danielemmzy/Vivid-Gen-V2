from fastapi import APIRouter
from starlette.responses import Response

from app.monitoring.health import liveness, readiness

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def health_live():
    return await liveness()


@router.get("/health/ready")
async def health_ready():
    result = await readiness()
    if result["status"] != "ready":
        return Response(content=str(result), status_code=503, media_type="application/json")
    return result

from time import perf_counter

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import ProviderAvailabilityStatus
from app.core.exceptions import InvalidGenerationParamsError, ProviderNotConfiguredError, VividGenError
from app.dependencies import current_user_id, db_session
from app.monitoring.metrics import media_import_total, media_search_total
from app.services.providers.stock.registry import get_stock_provider, list_stock_providers

router = APIRouter(prefix="/media", tags=["media"])


class StockProviderRequestError(VividGenError):
    http_status = 502
    code = "STOCK_PROVIDER_FAILED"


class DownloadRequest(BaseModel):
    key: str = Field(min_length=1, max_length=1024)


class StockSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=160)
    kind: str = Field(default="video", pattern=r"^(image|video)$")
    orientation: str | None = Field(default=None, pattern=r"^(landscape|portrait|square)$")
    provider: str = Field(default="pexels", pattern=r"^[a-z0-9_-]{1,32}$")
    limit: int = Field(default=8, ge=1, le=15)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Enter at least two characters to search stock media")
        return value


class StockImportRequest(BaseModel):
    query: str = Field(min_length=2, max_length=160)
    external_id: str = Field(min_length=1, max_length=191)
    kind: str = Field(default="video", pattern=r"^(image|video)$")
    orientation: str | None = Field(default=None, pattern=r"^(landscape|portrait|square)$")
    provider: str = Field(default="pexels", pattern=r"^[a-z0-9_-]{1,32}$")


@router.post("/presign-download")
async def presign_download_endpoint(req: DownloadRequest, user_id: str = Depends(current_user_id)):
    from app.services.storage.s3 import presign_download
    owned = req.key.startswith(f"generations/{user_id}/") or req.key.startswith(f"uploads/{user_id}/")
    if not owned:
        from fastapi import HTTPException
        raise HTTPException(403, "Media key is not owned by this user")
    return {"url": presign_download(req.key)}


@router.get("/providers")
async def stock_providers(_user_id: str = Depends(current_user_id)):
    return {"providers": [{"name": provider.name, "status": provider.availability().value} for provider in list_stock_providers()]}


@router.post("/search")
async def search_stock_media(body: StockSearchRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    from app.services.entitlements import require_plan_feature
    await require_plan_feature(session, user_id, "stock_search")
    provider = get_stock_provider(body.provider)
    status = provider.availability()
    if status != ProviderAvailabilityStatus.AVAILABLE:
        media_search_total.labels(provider.name, body.kind, "not_configured").inc()
        raise ProviderNotConfiguredError(
            f"Stock media search is unavailable because {provider.name} is not configured.",
            details={"provider": provider.name, "status": status.value, "required_setting": "PEXELS_API_KEY" if provider.name == "pexels" else "provider_api_key"},
        )
    started = perf_counter()
    try:
        candidates = await provider.search(query=body.query, kind=body.kind, orientation=body.orientation, max_results=body.limit)
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        reason = "rate_limited" if status_code == 429 else "provider_error"
        media_search_total.labels(provider.name, body.kind, reason).inc()
        from app.orchestration import provider_health
        await provider_health.record_failure(session, provider=provider.name, capability=f"stock_{body.kind}", timeout="timeout" in str(exc).lower(), rate_limited=status_code == 429)
        raise StockProviderRequestError(
            "The stock media provider could not complete this search. Please retry in a moment.",
            details={"provider": provider.name, "reason": reason, "retryable": status_code is None or status_code == 429 or status_code >= 500},
        ) from exc
    media_search_total.labels(provider.name, body.kind, "success").inc()
    from app.orchestration import provider_health
    await provider_health.record_success(session, provider=provider.name, capability=f"stock_{body.kind}", latency_ms=(perf_counter() - started) * 1000)
    return {"provider": provider.name, "query": body.query, "kind": body.kind, "results": [
        {"external_id": item.external_id, "preview_url": item.preview_url, "width": item.width,
         "height": item.height, "duration_seconds": item.duration_seconds, "license": item.license,
         "attribution": item.attribution, "content_type": item.content_type}
        for item in candidates if item.external_id and item.preview_url
    ], "count": len(candidates)}


@router.post("/import-stock")
async def import_stock_media(body: StockImportRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    provider = get_stock_provider(body.provider)
    if provider.availability() != ProviderAvailabilityStatus.AVAILABLE:
        media_import_total.labels(provider.name, body.kind, "not_configured").inc()
        raise ProviderNotConfiguredError("Stock media import is not configured.", details={"provider": provider.name})
    try:
        started = perf_counter()
        candidates = await provider.search(query=body.query, kind=body.kind, orientation=body.orientation, max_results=15)
        selected = next((candidate for candidate in candidates if candidate.external_id == body.external_id), None)
        if not selected or not selected.url:
            raise InvalidGenerationParamsError("That stock result is no longer available. Search again and choose another result.")
        from app.services.providers.stock.importer import import_stock_candidate
        imported = await import_stock_candidate(selected, user_id=user_id, kind=body.kind)
        media_import_total.labels(provider.name, body.kind, "success").inc()
        from app.orchestration import provider_health
        await provider_health.record_success(session, provider=provider.name, capability=f"stock_{body.kind}", latency_ms=(perf_counter() - started) * 1000)
        imported["provider"] = provider.name
        return imported
    except VividGenError:
        media_import_total.labels(provider.name, body.kind, "failed").inc()
        raise
    except Exception as exc:
        media_import_total.labels(provider.name, body.kind, "failed").inc()
        from app.orchestration import provider_health
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        await provider_health.record_failure(session, provider=provider.name, capability=f"stock_{body.kind}", timeout="timeout" in str(exc).lower(), rate_limited=status_code == 429)
        raise VividGenError("Couldn't import that stock result. The provider may have removed it or the download failed; search again or upload your own licensed media.", details={"provider": provider.name, "retryable": True}) from exc

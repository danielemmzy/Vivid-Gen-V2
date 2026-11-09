"""Import a provider-verified stock candidate into private user-owned storage."""
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.core.config import settings
from app.core.exceptions import InvalidGenerationParamsError
from app.core.safe_fetch import download_url_to_path
from app.services.storage.s3 import upload_from_path
from app.services.providers.stock.base import StockCandidate


async def import_stock_candidate(candidate: StockCandidate, *, user_id: str, kind: str) -> dict:
    if kind not in {"image", "video"} or not candidate.url:
        raise InvalidGenerationParamsError("The selected stock result has no importable media URL.")
    with TemporaryDirectory(prefix="vivid-stock-import-") as tmpdir:
        local_path = str(Path(tmpdir) / "asset")
        content_type = await download_url_to_path(candidate.url, local_path, max_bytes=settings.stock_asset_max_bytes)
        expected = "video/" if kind == "video" else "image/"
        if not content_type.startswith(expected):
            raise InvalidGenerationParamsError(
                "The stock provider returned an unexpected media type. Choose another result.",
                details={"content_type": content_type, "expected": expected},
            )
        extension = {
            "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
            "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
        }.get(content_type, ".mp4" if kind == "video" else ".jpg")
        key = f"{settings.s3_input_prefix.rstrip('/')}/{user_id}/media-reference/{uuid4().hex}{extension}"
        upload_from_path(local_path, key, content_type)
    return {"s3_key": key, "kind": kind, "content_type": content_type,
            "license": candidate.license, "attribution": candidate.attribution,
            "provider": "pexels", "external_id": candidate.external_id,
            "width": candidate.width, "height": candidate.height,
            "duration_seconds": candidate.duration_seconds}

"""gap-closure (0006): pragmatic substitute for a real stock-media
provider integration (P0 Pipeline F in the audit). This session has no
vendor API key for Pexels/Pixabay/Getty/etc., so a true "search stock
footage by keyword" capability cannot be built against anything real —
inventing one that calls nothing would be exactly the "pretend a
capability exists" failure mode this project's own operating rules
forbid.

What this DOES implement, and it's a real capability, not a stub: if a
`stock_video`/`stock_image` scene has a `stock_source_url` (a specific,
already-known URL — e.g. supplied directly by the user, or in the future
by an article-image-extraction step), it is fetched through the same
SSRF-safe path url_to_video.py uses, validated against the expected media
kind, and registered as a real Asset — no different in the end from a
`user_asset` scene except the file comes from a URL instead of a
pre-uploaded S3 key. This unblocks the common real case of "I already
have a stock clip I'm licensed to use, here's the URL" without needing a
search API. Keyword-based *search* remains genuinely unimplemented."""
import tempfile
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.core.exceptions import VividGenError
from app.core.logging import get_logger
from app.core.safe_fetch import UrlFetchError, check_robots_txt, download_url_to_path
from app.services.storage.s3 import upload_from_path

logger = get_logger(__name__)


class StockAssetFetchError(VividGenError):
    http_status = 422
    code = "STOCK_ASSET_FETCH_FAILED"


_EXPECTED_CONTENT_TYPE_PREFIX = {"stock_video": "video/", "stock_image": "image/"}


async def fetch_stock_asset(*, visual_type: str, source_url: str, user_id: str, project_id: str) -> tuple[str, str]:
    """Downloads `source_url` (SSRF-safe) and re-uploads it under this
    project's own S3 prefix — never hands out the original URL as-is to
    the render pipeline, so a since-changed or since-removed remote file
    can't silently break a render after the scene was approved. Returns
    (s3_key, content_type)."""
    await check_robots_txt(source_url)
    expected_prefix = _EXPECTED_CONTENT_TYPE_PREFIX.get(visual_type)
    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = str(Path(tmpdir) / f"stock_source_{uuid4().hex[:8]}")
        try:
            content_type = await download_url_to_path(source_url, local_path, max_bytes=settings.stock_asset_max_bytes)
        except UrlFetchError as exc:
            raise StockAssetFetchError(f"Couldn't fetch the stock asset URL: {exc.message}", details={"url": source_url}) from exc

        if expected_prefix and not content_type.startswith(expected_prefix):
            raise StockAssetFetchError(
                f"Expected a {expected_prefix.rstrip('/')} file for a {visual_type} scene, got '{content_type}'",
                details={"url": source_url, "content_type": content_type},
            )

        ext = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
               "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(content_type, "")
        output_key = f"{settings.s3_output_prefix}/{user_id}/projects/{project_id}/stock/{uuid4().hex}{ext}"
        upload_from_path(local_path, output_key, content_type or "application/octet-stream")
        logger.info("stock_asset_fetched", project_id=project_id, source_url=source_url, content_type=content_type)
        return output_key, content_type

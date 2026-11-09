"""Safe visual extraction helpers shared by URL and PowerPoint workflows.

Only public HTTP(S) images and embedded PPTX picture objects are imported.
The original source is kept as provenance metadata; failed optional visuals are
reported as warnings rather than turning a readable source into a failed plan.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse
from uuid import uuid4

from app.core.config import settings
import logging
from app.core.safe_fetch import UrlFetchError, assert_fetchable, check_robots_txt, download_url_to_path
from app.services.storage.s3 import upload_from_path

logger = logging.getLogger(__name__)

_IMAGE_CONTENT_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


async def import_public_image(url: str, *, user_id: str, purpose: str) -> tuple[str, str] | None:
    """SSRF-safe import of one remote image into the authenticated user's input prefix."""
    try:
        assert_fetchable(url)
        await check_robots_txt(url)
        with tempfile.TemporaryDirectory(prefix="vivid-source-image-") as tmpdir:
            local = str(Path(tmpdir) / "source-image")
            content_type = await download_url_to_path(url, local, max_bytes=settings.url_reference_max_image_bytes)
            if content_type not in _IMAGE_CONTENT_TYPES or Path(local).stat().st_size < 1024:
                return None
            key = f"{settings.s3_input_prefix.rstrip('/')}/{user_id}/{purpose}/{uuid4().hex}{_IMAGE_CONTENT_TYPES[content_type]}"
            upload_from_path(local, key, content_type)
            return key, content_type
    except Exception as exc:  # optional visual; preserve article/deck text extraction
        logger.info("source_visual_import_skipped", purpose=purpose, host=urlparse(url).hostname, reason=type(exc).__name__)
        return None


def extract_pptx_picture_bytes(local_path: str) -> tuple[list[tuple[bytes, str]], list[str]]:
    """Extract embedded slide pictures and useful chart/diagram labels from PPTX."""
    from pptx import Presentation

    deck = Presentation(local_path)
    images: list[tuple[bytes, str]] = []
    descriptions: list[str] = []
    for slide_number, slide in enumerate(deck.slides, start=1):
        slide_labels: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                value = " ".join((shape.text_frame.text or "").split())
                if value:
                    slide_labels.append(value)
            if getattr(shape, "shape_type", None) == 13 and getattr(shape, "image", None):
                try:
                    image = shape.image
                    ext = (image.ext or "png").lower()
                    if ext in {"jpg", "jpeg", "png", "webp", "gif"}:
                        images.append((image.blob, "jpg" if ext == "jpeg" else ext))
                except Exception as exc:  # corrupt/unsupported embedded image; keep reading the deck
                    logger.info("pptx_picture_skipped", slide=slide_number, reason=type(exc).__name__)
            if getattr(shape, "has_chart", False):
                try:
                    chart = shape.chart
                    title = ""
                    if chart.has_title:
                        title = " ".join(chart.chart_title.text_frame.text.split())
                    series_names = [str(series.name) for series in chart.series if getattr(series, "name", None)]
                    labels = []
                    try:
                        labels = [str(point.label) for point in chart.plots[0].categories]
                    except Exception:
                        pass
                    description = "; ".join(part for part in (title, "series: " + ", ".join(series_names) if series_names else "", "categories: " + ", ".join(labels[:12]) if labels else "") if part)
                    if description:
                        slide_labels.append("Chart details: " + description)
                except Exception as exc:
                    logger.info("pptx_chart_extraction_skipped", slide=slide_number, reason=type(exc).__name__)
        if slide_labels:
            descriptions.append(f"Slide {slide_number}: " + " | ".join(slide_labels))
        try:
            notes = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ""
            notes = " ".join((notes or "").split())
            if notes:
                descriptions.append(f"Slide {slide_number} speaker notes: {notes}")
        except Exception:
            pass
    return images, descriptions


def save_embedded_images(images: list[tuple[bytes, str]], *, user_id: str) -> list[str]:
    """Persist up to the configured number of embedded images in private storage."""
    import mimetypes
    keys: list[str] = []
    for content, ext in images[: settings.url_reference_max_images]:
        if len(content) < 1024 or len(content) > settings.url_reference_max_image_bytes:
            continue
        content_type = mimetypes.guess_type("source." + ext)[0] or "image/png"
        key = f"{settings.s3_input_prefix.rstrip('/')}/{user_id}/ppt-reference/{uuid4().hex}.{ext}"
        # upload_bytes avoids a temporary copy of the image payload on disk.
        from app.services.storage.s3 import upload_bytes
        upload_bytes(key, content, content_type)
        keys.append(key)
    return keys

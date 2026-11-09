"""Presentation -> Video with slide text, embedded image references, chart labels and speaker notes."""
import tempfile
from pathlib import Path
from pydantic import BaseModel, Field
from app.core.exceptions import VividGenError, InvalidGenerationParamsError
from app.core.config import settings
from app.services.storage.s3 import download_to_path
from app.workflows.visual_extraction import extract_pptx_picture_bytes, save_embedded_images


class PresentationRequest(BaseModel):
    pptx_s3_key: str
    duration_seconds: int = Field(default=90, ge=30, le=300)
    style: str | None = "corporate"
    language: str = "en"


class PptxExtractionError(VividGenError):
    http_status = 422
    code = "PPTX_EXTRACTION_FAILED"


def _extract_slide_text(local_path: str) -> str:
    from pptx import Presentation
    try:
        deck = Presentation(local_path)
    except Exception as exc:
        raise PptxExtractionError("Could not read this file as a .pptx presentation", details={"cause": type(exc).__name__}) from exc
    lines = []
    for i, slide in enumerate(deck.slides, start=1):
        texts = [shape.text_frame.text.strip() for shape in slide.shapes if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip()]
        if texts:
            lines.append(f"Slide {i}: " + " | ".join(texts))
    return "\n".join(lines)


async def build_plan_inputs(body: PresentationRequest, user_id: str | None = None) -> dict:
    if user_id:
        expected_prefix = f"{settings.s3_input_prefix.rstrip('/')}/{user_id}/presentationSource/"
        if not body.pptx_s3_key.startswith(expected_prefix) or ".." in body.pptx_s3_key.split("/"):
            raise InvalidGenerationParamsError("Presentation file must be an upload owned by this user.", details={"reason": "source_asset_not_owned"})
    with tempfile.TemporaryDirectory(prefix="vivid-pptx-") as tmpdir:
        local_path = str(Path(tmpdir) / "deck.pptx")
        try:
            download_to_path(body.pptx_s3_key, local_path)
            slide_text = _extract_slide_text(local_path)
            images, visual_descriptions = extract_pptx_picture_bytes(local_path)
        except PptxExtractionError:
            raise
        except Exception as exc:
            raise PptxExtractionError("Could not download or inspect this presentation. Re-upload a valid .pptx and try again.", details={"cause": type(exc).__name__}) from exc
        reference_keys = save_embedded_images(images, user_id=user_id) if user_id else []
    if not slide_text.strip() and not visual_descriptions and not reference_keys:
        raise PptxExtractionError("No slide text, embedded pictures, chart labels or speaker notes could be extracted from this presentation.")
    source_facts = slide_text[:12000]
    if visual_descriptions:
        source_facts += "\n\nSLIDE VISUAL/CHART/NOTES DETAILS:\n" + "\n".join(visual_descriptions)[:5000]
    if reference_keys:
        source_facts += f"\n\nImported {len(reference_keys)} embedded slide image(s) as private visual references. Use them to preserve the deck's product, people, diagrams and visual style."
    return {
        "prompt": f"Create a {body.duration_seconds}-second narrated video version of this presentation, preserving slide order and accurately representing its text, charts and visual material.",
        "project_type": "presentation",
        "duration_seconds": body.duration_seconds,
        "style": body.style,
        "language": body.language,
        "source_facts": source_facts[:15000],
        "reference_image_s3_keys": reference_keys,
        "source_pptx_s3_key": body.pptx_s3_key,
    }

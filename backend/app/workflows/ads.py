"""V2 Phase 17: Ad Studio (spec §39). A preset, not a separate engine —
this only builds the right prompt/source_facts for the SAME
`orchestration.planner.create_production_plan` every other workflow uses.
No new generation logic lives here.
"""
from pydantic import BaseModel, Field


class AdStudioRequest(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    product_description: str = Field(min_length=1, max_length=3000)  # real facts, not invented — becomes source_facts
    audience: str | None = None
    goal: str | None = None  # e.g. "increase purchases", "drive signups"
    platform: str = "instagram_reels"
    style: str | None = "cinematic"
    duration_seconds: int = Field(default=30, ge=10, le=90)
    language: str = "en"


def build_plan_inputs(body: AdStudioRequest) -> dict:
    """Returns kwargs for `planner.create_production_plan`. `source_facts`
    carries the real product description so the Director can't invent
    product claims (spec §18, §41) — it's told explicitly to only use
    what's here."""
    return {
        "prompt": (
            f"Create a {body.duration_seconds}-second advertisement for {body.product_name}. "
            f"Goal: {body.goal or 'drive interest and conversions'}."
        ),
        "project_type": "advertisement",
        "duration_seconds": body.duration_seconds,
        "target_platform": body.platform,
        "style": body.style,
        "audience": body.audience,
        "language": body.language,
        "source_facts": f"Product: {body.product_name}\nDescription: {body.product_description}",
    }

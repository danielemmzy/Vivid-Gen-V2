"""V2 Phase 18: Product Video (spec §41) — same pattern as ads.py, a
thinner preset (no explicit goal/audience framing, just product facts)."""
from pydantic import BaseModel, Field


class ProductVideoRequest(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    product_description: str = Field(min_length=1, max_length=3000)
    features: list[str] = Field(default_factory=list, max_length=10)
    duration_seconds: int = Field(default=30, ge=15, le=120)
    language: str = "en"


def build_plan_inputs(body: ProductVideoRequest) -> dict:
    facts = f"Product: {body.product_name}\nDescription: {body.product_description}"
    if body.features:
        facts += "\nFeatures:\n" + "\n".join(f"- {f}" for f in body.features)
    return {
        "prompt": f"Create a {body.duration_seconds}-second product showcase video for {body.product_name}.",
        "project_type": "product_video",
        "duration_seconds": body.duration_seconds,
        "language": body.language,
        "source_facts": facts,
    }

"""V2 Phase 20: YouTube long-form (spec §38). Longer duration, no
advertisement framing. Research/factual grounding (spec: "research must be
factually grounded") is NOT implemented here — this preset does not fetch
real facts about the topic, so the Director is working from its own
training knowledge only, same caveat as asking any LLM a factual
question. If real research grounding is wanted, this needs a real search
step first (e.g. reusing url_to_video.py's fetch+extract on a few search
results) — flagged, not built, since it needs a search API this session
has no credentials for."""
from pydantic import BaseModel, Field


class YouTubeRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    duration_seconds: int = Field(default=180, ge=60, le=600)
    style: str | None = None
    audience: str | None = None
    language: str = "en"


def build_plan_inputs(body: YouTubeRequest) -> dict:
    return {
        "prompt": f"Create a YouTube video explaining: {body.topic}",
        "project_type": "youtube",
        "duration_seconds": body.duration_seconds,
        "target_platform": "youtube",
        "style": body.style,
        "audience": body.audience,
        "language": body.language,
        # Deliberately no source_facts — see module docstring on the
        # research-grounding gap.
    }

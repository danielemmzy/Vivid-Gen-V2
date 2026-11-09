"""V2 Phase 15 (spec §37): highlight detection for Shorts/Repurpose.

Deliberately NOT part of planner.py/ProductionPlan — that pipeline plans
NEW scenes to generate; this one selects time ranges from footage that
already exists (an uploaded video's transcript). Different enough
capability (spec §37 explicitly separates this from simple fixed-interval
splitting: "rather than simply splitting the video every N seconds") that
forcing it through ProductionPlan would mean ScenePlan fields like
visual_prompt/requires_character_reference that make no sense here.
"""
from pydantic import BaseModel, Field

from app.core.config import settings
from app.orchestration.planner import PlannerError, InvalidPlanError, get_llm_client


class HighlightCandidate(BaseModel):
    start_seconds: float
    end_seconds: float
    reason: str  # why this is a good clip: "hook", "punchline", "key statistic", "emotional moment", ...
    hook_score: float = Field(ge=0, le=1)  # the Director's own confidence this clip stands alone


class HighlightPlan(BaseModel):
    candidates: list[HighlightCandidate] = Field(min_length=1, max_length=10)


_SCHEMA = HighlightPlan.model_json_schema()

_SYSTEM_PROMPT = """You identify the strongest short-form clips from a video
transcript with timestamps. Look for hooks, punchlines, standalone
statements, surprising claims, and emotionally resonant moments — not
arbitrary fixed-length slices. Each candidate must make sense understood
entirely on its own, with no context from the rest of the video. Only use
timestamps that appear in the provided transcript segments — never invent
a timestamp."""


async def detect_highlights(*, transcript_segments: list[dict], max_candidates: int = 5) -> HighlightPlan:
    transcript_text = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in transcript_segments)
    client = get_llm_client()
    try:
        response = await client.messages.create(
            model=settings.director_model,
            max_tokens=settings.director_max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Find up to {max_candidates} highlight clips:\n\n{transcript_text}"}],
            tools=[{"name": "submit_highlights", "description": "Submit the highlight candidates.", "input_schema": _SCHEMA}],
            tool_choice={"type": "tool", "name": "submit_highlights"},
        )
    except Exception as exc:  # noqa: BLE001
        raise PlannerError("Highlight detection request failed", details={"cause": str(exc)}) from exc

    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        raise InvalidPlanError("Highlight detection did not return structured output")
    return HighlightPlan.model_validate(tool_use.input)

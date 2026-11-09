"""V2 Phase 4: the AI Director.

Converts user intent (a prompt, plus optional platform/duration/style/
audience/brand hints) into a ProductionPlan. This is the one new LLM call
site in the whole codebase — nothing else here talks to an LLM.

Architectural rule this file must never violate (spec §13, §15): the
Director NEVER calls a generation provider (fal/modal/etc) directly. It
only returns a ProductionPlan; executor.py is solely responsible for
turning that into real Shots, and model_router.py is solely responsible
for picking which model executes each one. Keeping this boundary is what
lets the LLM vendor, the video provider, and the routing logic all change
independently without touching each other.

Safety rules enforced here, not left to prompt-engineering alone (spec
§18): the Director is instructed never to invent product facts, and the
caller is expected to pass real `source_facts` (e.g. actual product
description/specs, or actual article text for a URL workflow) rather than
letting the model fill gaps with invented specifics. This module doesn't
fetch those facts itself — see workflows/ for that.
"""
import json

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import VividGenError
from app.orchestration.production_plan import ProductionPlan

_PLAN_TOOL_SCHEMA = ProductionPlan.model_json_schema()

_SYSTEM_PROMPT = """You are the AI Director for Vivid Gen, a video production platform.

Your job: turn a user's plain-language request into a structured, shootable
ProductionPlan — a script broken into scenes, each with a concrete visual
prompt a text-to-video/text-to-image model could actually generate from.

Rules you must follow:
- Never invent facts about a real product, brand, article, or person. If the
  caller gave you `source_facts`, only use what's in there. If they gave you
  none and the request implies specific real-world facts you don't have,
  write generic scenes that don't depend on facts you don't have, rather
  than fabricating specifics (fake statistics, invented product features,
  invented quotes).
- The sum of every scene's duration_seconds MUST equal the requested duration_seconds exactly; the backend will split each scene into model-supported clips and trim the final clip of a scene to its planned timeline length.
- Set continuity_mode to "previous_final_frame" only when a scene should continue the action/state of the preceding scene; use "character" with a valid character_id for identity anchoring, otherwise use "none". Never invent a reference_scene_number.
- Set budget_profile to "short_form" for a finished video of 60 seconds or less, otherwise "long_form" (maximum 600 seconds).
- Each scene's visual_prompt must be self-contained and concrete enough to
  hand directly to a video generation model — describe the shot, not the
  marketing idea behind it.
- Only enable voiceover/music/ambience/captions/branding if the user asked for them
  or they're clearly implied by the project_type (e.g. an "advertisement"
  almost always wants a CTA scene and usually wants voiceover+captions).
- When voiceover.enabled is true, include a concise, speakable voiceover_line
  for every scene that needs narration; never enable narration with no lines.
- Keep music and ambience optional. Prefer an instrumental bed without lyrics;
  ambience.prompt should describe environmental sound only, not music or speech.
- quality_mode should be "medium" unless the user specifically asks for
  lower-cost/faster generation or highest quality.
- If a list of existing characters is provided below, and a scene should
  show one of them (a recurring person, or a product whose reference
  photos were uploaded as a "character"), set that scene's character_id to
  the matching character's id and set requires_character_reference (or
  requires_product_reference, for a product) to true. Only ever use a
  character_id from that exact list — never invent one.
"""


class PlannerError(VividGenError):
    http_status = 502
    code = "PLANNER_FAILED"


class InvalidPlanError(VividGenError):
    http_status = 502
    code = "INVALID_PLAN"


def get_llm_client() -> AsyncOpenAI:
    if not settings.openai_api_key:
        raise PlannerError(
            "AI Director is not configured", details={"missing": "OPENAI_API_KEY"}
        )
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def create_production_plan(
    *,
    prompt: str,
    project_type: str = "video",
    duration_seconds: int | None = None,
    aspect_ratio: str | None = None,
    target_platform: str | None = None,
    style: str | None = None,
    audience: str | None = None,
    language: str = "en",
    source_facts: str | None = None,
    existing_characters: list[dict] | None = None,
) -> ProductionPlan:
    """The single entry point every workflow (prompt->video, ads, YouTube,
    product video, URL->video, ...) calls. Workflow-specific behavior comes
    from how the *caller* builds `prompt`/`source_facts`/`project_type` —
    this function itself has no per-workflow branching, per the spec's
    "workflows are presets, not separate engines" rule (§31).

    gap-closure: `existing_characters` (each `{"id": ..., "name": ...,
    "description": ...}`) is new — previously the Director had no way to
    know a Character already existed on this project, so
    ScenePlan.requires_character_reference/requires_product_reference were
    declared and never actionable. Passing this list lets the Director
    reference one by id (see ScenePlan.character_id), which executor.py
    then threads through to the actual generation."""
    user_message = _build_user_message(
        prompt=prompt, project_type=project_type, duration_seconds=duration_seconds,
        aspect_ratio=aspect_ratio, target_platform=target_platform, style=style,
        audience=audience, language=language, source_facts=source_facts,
        existing_characters=existing_characters,
    )

    client = get_llm_client()
    try:
        response = await client.chat.completions.create(
            model=settings.director_model,
            max_tokens=settings.director_max_tokens,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            tools=[{
                "type": "function",
                "function": {
                    "name": "submit_production_plan",
                    "description": "Submit the finished ProductionPlan.",
                    "parameters": _PLAN_TOOL_SCHEMA,
                },
            }],
            tool_choice={
                "type": "function",
                "function": {"name": "submit_production_plan"},
            },
            parallel_tool_calls=False,
        )
    except Exception as exc:  # network/API errors from the OpenAI SDK
        raise PlannerError("AI Director request failed", details={"cause": str(exc)}) from exc

    message = response.choices[0].message if response.choices else None
    tool_call = next(
        (call for call in (message.tool_calls or []) if call.function.name == "submit_production_plan"),
        None,
    ) if message else None
    if tool_call is None:
        raise InvalidPlanError("AI Director did not return a structured plan")

    try:
        plan_data = json.loads(tool_call.function.arguments)
        return ProductionPlan.model_validate(plan_data)
    except (ValidationError, json.JSONDecodeError) as exc:
        errors = json.loads(exc.json()) if isinstance(exc, ValidationError) else {"message": str(exc)}
        raise InvalidPlanError("AI Director returned an invalid plan", details={"errors": errors}) from exc


def _build_user_message(
    *, prompt: str, project_type: str, duration_seconds: int | None, aspect_ratio: str | None,
    target_platform: str | None, style: str | None, audience: str | None, language: str,
    source_facts: str | None, existing_characters: list[dict] | None = None,
) -> str:
    lines = [f"Request: {prompt}", f"project_type: {project_type}", f"language: {language}"]
    if duration_seconds:
        lines.append(f"duration_seconds: {duration_seconds}")
    if aspect_ratio:
        lines.append(f"aspect_ratio: {aspect_ratio}")
    if target_platform:
        lines.append(f"target_platform: {target_platform}")
    if style:
        lines.append(f"style: {style}")
    if audience:
        lines.append(f"audience: {audience}")
    if source_facts:
        lines.append(
            "source_facts (ONLY use these for any real-world claims — do not "
            f"invent anything beyond them):\n{source_facts}"
        )
    if existing_characters:
        char_lines = "\n".join(f"- id={c['id']}, name={c['name']}" for c in existing_characters)
        lines.append(
            "existing_characters (reference these by id in a scene's "
            f"character_id if that scene should feature one of them):\n{char_lines}"
        )
    return "\n".join(lines)

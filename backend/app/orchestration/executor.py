"""gap-closure (0007): Production creation + DAG construction.

Previously (rounds 1-2) this file mapped a ProductionPlan directly onto
Shots via a flat loop, with the plan itself living in
`Project.metadata_json` and no object representing "this production
run" at all. Now:

  POST /plan          -> create_production_for_plan: creates a Production
                         (planning) + ProductionPlanRecord (draft).
  POST /approve-plan  -> execute_plan: validates, creates Shots for each
                         scene, builds the real DAG (orchestration/dag.py)
                         — SCENE/VOICE/CAPTIONS/MUSIC/BRANDING/RENDER
                         tasks with real dependency edges — and creates
                         the ProductionBudget estimate. Does NOT enqueue
                         anything (still spends no credits — see spec
                         §16/§53, preserved from rounds 1-2).
  POST /generate      -> (routers/projects.py) reserves the budget and
                         calls scheduler.start_production, which is the
                         only place a task is enqueued without having
                         been triggered by another task's completion.

`Project.metadata_json` is still written as a one-release legacy
fallback (`load_plan`) for any project created before this migration
that somehow still needs the old lookup path — new code reads the plan
from ProductionPlanRecord via `load_plan_record`, not from there.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import (
    GenerationType,
    ProductionPlanStatus,
    ProductionStatus,
    ProductionTaskStatus,
    ProductionTaskType,
    ProjectStatus,
)
from app.core.exceptions import InvalidGenerationParamsError
from app.core.logging import get_logger
from app.models.product import Product
from app.models.production import Production
from app.models.production_plan import ProductionPlanRecord
from app.models.project import Character, Project, Shot
from app.orchestration import asset_router, dag
from app.orchestration.asset_fetch import StockAssetFetchError, fetch_stock_asset
from app.orchestration.dag import DagSpec, TaskSpec
from app.orchestration.model_router import NoRoutableModelError, RoutingRequest, select_model
from app.orchestration.production_plan import ProductionPlan, ScenePlan
from app.orchestration.duration_planner import choose_supported_clip_duration
from app.orchestration.state_machine import assert_transition
from app.services.movie.service import MovieService
from app.services.production.budget_service import ProductionBudgetService
from app.services.providers.fal.catalog import MODELS
from app.services.providers.registry import provider_is_configured

logger = get_logger(__name__)

# See is_scene_executable below.
_EXECUTABLE_VISUAL_TYPES = {"generated_video", "user_asset"}
_URL_FETCHABLE_VISUAL_TYPES = {"stock_video"}


def is_scene_executable(scene: ScenePlan) -> bool:
    """Single source of truth for visuals that can produce a video track.

    A stock image is not a video clip; it must be used as a reference for a
    generated-video scene rather than being passed to the movie concat path.
    """
    if scene.visual_type in _EXECUTABLE_VISUAL_TYPES:
        return True
    if scene.visual_type == "stock_video":
        return bool(scene.stock_source_url)
    return False


@dataclass
class ExecutionResult:
    project_id: str
    production_id: str
    created_shots: list[Shot] = field(default_factory=list)
    skipped_scenes: list[dict] = field(default_factory=list)  # [{scene_number, reason}]
    warnings: list[str] = field(default_factory=list)


async def create_production_for_plan(
    session: AsyncSession, user_id: str, project: Project, plan: ProductionPlan, director_input: dict[str, Any] | None = None,
) -> Production:
    """Called from POST /plan, after the Director call succeeds. Creates
    the first-class Production a project's plan/approve/generate cycle
    now always has, and a versioned ProductionPlanRecord (version 1 for
    a brand-new production — a re-plan on the same project starts a NEW
    Production, it does not bump the version on an old one, matching the
    round-3 decision that a project can have multiple production runs)."""
    assert_transition(project.status, ProjectStatus.AWAITING_APPROVAL)
    from app.services.entitlements import enforce_project_entitlement
    await enforce_project_entitlement(session, user_id, plan.duration_seconds)

    production = Production(
        id="prod_" + uuid4().hex, project_id=project.id, user_id=user_id,
        status=ProductionStatus.AWAITING_APPROVAL, planning_status=ProductionStatus.AWAITING_APPROVAL,
        execution_status=ProductionStatus.DRAFT, production_type=plan.project_type,
    )
    session.add(production)
    await session.flush()

    session.add(ProductionPlanRecord(
        id="pplan_" + uuid4().hex, production_id=production.id, project_id=project.id, user_id=user_id,
        version=1, status=ProductionPlanStatus.DRAFT, director_input=director_input, plan_json=plan.model_dump(mode="json"),
    ))

    project.current_production_id = production.id
    project.status = ProjectStatus.AWAITING_APPROVAL
    # Legacy fallback only — see module docstring. New code never reads
    # this back; `load_plan_record` is the canonical read path now.
    project.metadata_json = {**(project.metadata_json or {}), "production_plan": plan.model_dump(mode="json")}
    await session.commit()
    logger.info("production_created", production_id=production.id, project_id=project.id)
    return production


async def load_plan_record(session: AsyncSession, production_id: str) -> ProductionPlanRecord | None:
    return (
        await session.execute(select(ProductionPlanRecord).where(ProductionPlanRecord.production_id == production_id))
    ).scalar_one_or_none()


async def load_plan_for_project(session: AsyncSession, project: Project) -> tuple[Production | None, ProductionPlan | None]:
    """Canonical read path: follow project.current_production_id to its
    ProductionPlanRecord. Falls back to the legacy Project.metadata_json
    blob only if no Production exists at all (a project untouched since
    before this migration)."""
    if project.current_production_id:
        production = await session.get(Production, project.current_production_id)
        record = await load_plan_record(session, project.current_production_id)
        if record:
            return production, ProductionPlan.model_validate(record.plan_json)
    raw = (project.metadata_json or {}).get("production_plan")
    return None, (ProductionPlan.model_validate(raw) if raw else None)


def load_plan(project: Project) -> ProductionPlan | None:
    """Deprecated synchronous legacy accessor — kept only because it has
    no `session` argument and some old call sites may still expect that
    shape. Reads ONLY the legacy metadata_json blob; prefer
    `load_plan_for_project` (async, reads the real ProductionPlanRecord)
    everywhere new code touches this."""
    raw = (project.metadata_json or {}).get("production_plan")
    return ProductionPlan.model_validate(raw) if raw else None


async def execute_plan(
    session: AsyncSession, user_id: str, project: Project, plan: ProductionPlan,
) -> ExecutionResult:
    """Approval step. `plan` may be a user-edited version of what the
    Director originally proposed (the caller — routers/projects.py's
    approve_plan — accepts an optional edited plan in the request body);
    whatever is passed here becomes the ProductionPlanRecord's approved
    plan_json, which is the ground truth of what actually got built,
    not necessarily what the Director first drafted.

    Still spends no credits — shots are created, and the DAG is fully
    built and validated, but nothing is enqueued (see
    orchestration/scheduler.py's start_production, called only from
    POST /generate)."""
    assert_transition(project.status, ProjectStatus.GENERATING)
    if not project.current_production_id:
        raise ValueError("execute_plan called on a project with no Production — call POST /plan first")
    production = await session.get(Production, project.current_production_id)
    plan_record = await load_plan_record(session, production.id)

    from app.services.entitlements import enforce_project_entitlement
    await enforce_project_entitlement(session, user_id, plan.duration_seconds, exclude_project_id=project.id)

    movie = MovieService(session)
    existing_project_shots = await movie.repo.get_shots(project.id)
    next_order_index = len(existing_project_shots)
    result = ExecutionResult(project_id=project.id, production_id=production.id)
    spec = DagSpec()
    scene_keys: list[str] = []
    scene_first_task_key_by_number: dict[int, str] = {}
    scene_last_task_key_by_number: dict[int, str] = {}
    active_reference_number_by_scene: dict[int, int] = {}
    scene_task_keys_by_number: dict[int, list[str]] = {}
    last_shot_by_scene_number: dict[int, Shot] = {}
    ordered_scenes = sorted(plan.scenes, key=lambda s: s.scene_number)
    previous_scene_number: int | None = None
    reference_number_by_scene: dict[int, int] = {}

    from app.services.providers.fal.catalog import get_model
    from app.services.generation.capabilities import get_capabilities

    for scene in ordered_scenes:
        reference_number = scene.reference_scene_number
        if reference_number is None and scene.continuity_mode == "previous_final_frame":
            reference_number = previous_scene_number
        if reference_number is not None:
            reference_number_by_scene[scene.scene_number] = reference_number
        previous_scene_number = scene.scene_number

        task_keys: list[str] = []
        scene_task_keys_by_number[scene.scene_number] = task_keys

        def add_scene_task(task_key: str, shot: Shot | None, *, status: str | None = None, error: str | None = None) -> None:
            task_keys.append(task_key)
            scene_keys.append(task_key)
            spec.add_task(task_key, TaskSpec(
                type=ProductionTaskType.SCENE, scene_number=scene.scene_number,
                shot_id=shot.id if shot else None, initial_status=status, error=error,
            ))

        if not is_scene_executable(scene):
            if scene.visual_type == "stock_video":
                reason = "visual_type 'stock_video' needs a stock_source_url" if not scene.stock_source_url else "stock_video source could not be routed"
            elif scene.visual_type == "stock_image":
                reason = "stock_image is a reference-only source, not a standalone video track; use it to condition a generated_video scene"
            else:
                reason = f"visual_type '{scene.visual_type}' has no generation provider yet"
            result.skipped_scenes.append({"scene_number": scene.scene_number, "reason": reason})
            add_scene_task(f"scene_{scene.scene_number}_shot_1", None, status=ProductionTaskStatus.SKIPPED, error=reason)
            scene_first_task_key_by_number[scene.scene_number] = task_keys[0]
            scene_last_task_key_by_number[scene.scene_number] = task_keys[-1]
            continue

        if scene.visual_type in _URL_FETCHABLE_VISUAL_TYPES:
            try:
                s3_key, _content_type = await fetch_stock_asset(
                    visual_type=scene.visual_type, source_url=scene.stock_source_url, user_id=user_id, project_id=project.id,
                )
            except StockAssetFetchError as exc:
                reason = f"stock_source_url fetch failed: {exc.message}"
                result.skipped_scenes.append({"scene_number": scene.scene_number, "reason": reason})
                add_scene_task(f"scene_{scene.scene_number}_shot_1", None, status=ProductionTaskStatus.SKIPPED, error=reason)
                scene_first_task_key_by_number[scene.scene_number] = task_keys[0]
                scene_last_task_key_by_number[scene.scene_number] = task_keys[-1]
                continue
            shot = await movie.add_user_asset_shot(
                user_id, project.id, s3_key=s3_key, prompt=scene.visual_prompt, camera_notes=scene.camera_notes,
                duration_seconds=scene.duration_seconds, scene_number=scene.scene_number, production_id=production.id,
                order_index=next_order_index, commit=False, enforce_limit=False, project_record=project,
            )
            next_order_index += 1
            result.created_shots.append(shot)
            add_scene_task(f"scene_{scene.scene_number}_shot_1", shot, status=ProductionTaskStatus.COMPLETED)
            last_shot_by_scene_number[scene.scene_number] = shot
            scene_first_task_key_by_number[scene.scene_number] = task_keys[0]
            scene_last_task_key_by_number[scene.scene_number] = task_keys[-1]
            continue

        if scene.visual_type == "user_asset":
            if not scene.source_asset_s3_key:
                reason = "visual_type 'user_asset' has no source_asset_s3_key"
                result.skipped_scenes.append({"scene_number": scene.scene_number, "reason": reason})
                add_scene_task(f"scene_{scene.scene_number}_shot_1", None, status=ProductionTaskStatus.SKIPPED, error=reason)
                scene_first_task_key_by_number[scene.scene_number] = task_keys[0]
                scene_last_task_key_by_number[scene.scene_number] = task_keys[-1]
                continue
            shot = await movie.add_user_asset_shot(
                user_id, project.id, s3_key=scene.source_asset_s3_key, prompt=scene.visual_prompt, camera_notes=scene.camera_notes,
                duration_seconds=scene.duration_seconds, scene_number=scene.scene_number, production_id=production.id,
                order_index=next_order_index, commit=False, enforce_limit=False, project_record=project,
            )
            next_order_index += 1
            result.created_shots.append(shot)
            add_scene_task(f"scene_{scene.scene_number}_shot_1", shot, status=ProductionTaskStatus.COMPLETED)
            last_shot_by_scene_number[scene.scene_number] = shot
            scene_first_task_key_by_number[scene.scene_number] = task_keys[0]
            scene_last_task_key_by_number[scene.scene_number] = task_keys[-1]
            continue

        character_ids = [scene.character_id] if scene.character_id else []
        first_model_id = await _route_scene(session, scene, plan)
        first_uses_reference = bool(
            scene.continuity_mode != "none" or reference_number is not None or scene.character_id or scene.product_id or scene.reference_image_s3_key
        )
        effective_continuity_mode = scene.continuity_mode
        if first_model_id is None and first_uses_reference:
            # Keep the requested finished duration achievable even when the
            # configured model has no image-conditioning route. Fall back to
            # text-to-video and explicitly warn that reference conditioning
            # is unavailable for this scene.
            text_only_scene = scene.model_copy(update={
                "continuity_mode": "none", "reference_scene_number": None,
                "character_id": None, "product_id": None, "reference_image_s3_key": None,
            })
            first_model_id = await _route_scene(session, text_only_scene, plan)
            if first_model_id:
                first_uses_reference = False
                effective_continuity_mode = "none"
                result.warnings.append(
                    f"Scene {scene.scene_number}: the configured models cannot apply its requested reference/continuity; "
                    "this scene will use text-to-video prompts, so visual continuity may be weaker."
                )
        if first_model_id is None:
            raise InvalidGenerationParamsError(
                f"Scene {scene.scene_number} has no configured model route for its required input mode.",
                details={"scene_number": scene.scene_number, "visual_type": scene.visual_type,
                         "requires_image_conditioning": first_uses_reference},
            )

        referenced_shot = last_shot_by_scene_number.get(reference_number) if reference_number is not None else None
        if first_uses_reference and reference_number is not None and referenced_shot is None:
            raise InvalidGenerationParamsError(
                f"Scene {scene.scene_number} requires the final frame from scene {reference_number}, but that scene has no usable shot.",
                details={"scene_number": scene.scene_number, "reference_scene_number": reference_number},
            )
        if not first_uses_reference:
            referenced_shot = None
        elif referenced_shot and reference_number is not None:
            active_reference_number_by_scene[scene.scene_number] = reference_number

        continuation_scene = scene.model_copy(update={"continuity_mode": "previous_final_frame", "reference_scene_number": None})
        continuation_model_id = await _route_scene(session, continuation_scene, plan)
        continuation_reference_mode = "previous_final_frame" if continuation_model_id else None
        first_model = get_model(first_model_id)
        first_options = sorted(set((get_capabilities(first_model).get("duration_options") or [])))
        if not first_options:
            raise InvalidGenerationParamsError(f"Model {first_model_id} has no verified shot-duration options.")
        if scene.duration_seconds > max(first_options) and not continuation_model_id:
            # A T2V-only route can still make a long movie from independent
            # clips; it just cannot condition each next clip on the prior end
            # frame. Prefer the original T2V route, otherwise retain a valid
            # image-conditioned route when a character/product reference exists.
            first_model_type = (first_model or {}).get("type")
            if first_model_type == "text_to_video":
                continuation_model_id = first_model_id
                continuation_reference_mode = None
            elif referenced_shot is not None:
                # If no continuation route is available, reuse the existing
                # scene reference for each segment instead of refusing the
                # finished duration. These clips can run in parallel after
                # the source scene is complete.
                continuation_model_id = first_model_id
                continuation_reference_mode = "scene_reference"
            elif scene.character_id or scene.product_id:
                continuation_model_id = first_model_id
                continuation_reference_mode = "character_product"
            elif scene.reference_image_s3_key:
                continuation_model_id = first_model_id
                continuation_reference_mode = "static_image"
            else:
                text_only_scene = scene.model_copy(update={
                    "continuity_mode": "none", "reference_scene_number": None,
                    "character_id": None, "product_id": None, "reference_image_s3_key": None,
                })
                text_model_id = await _route_scene(session, text_only_scene, plan)
                if text_model_id:
                    continuation_model_id = text_model_id
                    continuation_reference_mode = None
                else:
                    raise InvalidGenerationParamsError(
                        f"Scene {scene.scene_number} needs multiple clips, but no supported continuation route is configured.",
                        details={"scene_number": scene.scene_number, "duration_seconds": scene.duration_seconds},
                    )
            result.warnings.append(
                f"Scene {scene.scene_number}: no image-to-video continuation route is available; remaining clips will be "
                "generated independently and assembled in order."
            )

        remaining = float(scene.duration_seconds)
        previous_shot: Shot | None = None
        segment_index = 0
        previous_task_key: str | None = None

        while remaining > 0.001:
            segment_index += 1
            model_id = first_model_id if segment_index == 1 else continuation_model_id
            if not model_id:
                raise InvalidGenerationParamsError(
                    f"Scene {scene.scene_number} needs multiple clips, but no supported continuation route is configured.",
                    details={"scene_number": scene.scene_number, "remaining_seconds": remaining},
                )
            model = get_model(model_id)
            options = sorted(set(get_capabilities(model).get("duration_options") or []))
            if not options:
                raise InvalidGenerationParamsError(f"Model {model_id} has no verified shot-duration options.")
            inference_duration, timeline_duration = choose_supported_clip_duration(remaining, options)
            shot_prompt = scene.visual_prompt
            if segment_index > 1:
                if continuation_reference_mode == "previous_final_frame":
                    shot_prompt += (
                        " Continue seamlessly from the supplied previous-shot final frame. "
                        "Advance the action naturally; do not repeat the opening pose or recreate the same composition."
                    )
                elif continuation_reference_mode == "character_product":
                    shot_prompt += " Maintain the supplied character/product identity while advancing the action and varying the composition."
                else:
                    shot_prompt += " Continue the same scene and story beat; preserve the established style and action while varying the composition."

            if segment_index == 1:
                shot_reference = referenced_shot if first_uses_reference else None
                shot_character_ids = character_ids if first_uses_reference else []
                shot_product_id = scene.product_id if first_uses_reference else None
                if shot_reference:
                    shot_continuity = "previous_final_frame" if effective_continuity_mode == "previous_final_frame" else "scene_reference"
                elif shot_character_ids:
                    shot_continuity = "character"
                else:
                    shot_continuity = "none"
            elif continuation_reference_mode == "previous_final_frame":
                shot_reference = previous_shot
                shot_character_ids = []
                shot_product_id = None
                shot_continuity = "previous_final_frame"
            elif continuation_reference_mode == "scene_reference":
                shot_reference = referenced_shot
                shot_character_ids = []
                shot_product_id = None
                shot_continuity = "scene_reference"
            elif continuation_reference_mode == "character_product":
                shot_reference = None
                shot_character_ids = character_ids
                shot_product_id = scene.product_id
                shot_continuity = "character" if shot_character_ids else "none"
            elif continuation_reference_mode == "static_image":
                shot_reference = None
                shot_character_ids = []
                shot_product_id = None
                shot_continuity = "none"
            else:
                shot_reference = None
                shot_character_ids = []
                shot_product_id = None
                shot_continuity = "none"

            shot = await movie.add_shot(
                user_id, project.id, prompt=shot_prompt, camera_notes=scene.camera_notes,
                duration_seconds=inference_duration, character_ids=shot_character_ids, model_id=model_id,
                scene_number=scene.scene_number, production_id=production.id, product_id=shot_product_id,
                reference_shot_id=shot_reference.id if shot_reference else None,
                continuity_mode=shot_continuity, timeline_duration_seconds=timeline_duration,
                reference_image_s3_key=scene.reference_image_s3_key if (segment_index == 1 or continuation_reference_mode == "static_image") else None,
                order_index=next_order_index, commit=False, enforce_limit=False, project_record=project,
            )
            next_order_index += 1
            result.created_shots.append(shot)
            task_key = f"scene_{scene.scene_number}_shot_{segment_index}"
            add_scene_task(task_key, shot)
            if previous_task_key and continuation_reference_mode == "previous_final_frame":
                spec.add_edge(previous_task_key, task_key)
            elif segment_index > 1 and continuation_reference_mode == "scene_reference" and reference_number is not None:
                source_task_key = scene_last_task_key_by_number.get(reference_number)
                if source_task_key:
                    spec.add_edge(source_task_key, task_key)
            previous_task_key = task_key
            previous_shot = shot
            remaining = round(remaining - timeline_duration, 3)

        last_shot_by_scene_number[scene.scene_number] = previous_shot  # type: ignore[assignment]
        scene_first_task_key_by_number[scene.scene_number] = task_keys[0]
        scene_last_task_key_by_number[scene.scene_number] = task_keys[-1]

    # Persist cross-scene dependencies from the source scene's final clip to
    # the dependent scene's first clip. The DAG prevents premature inference.
    for scene_number, reference_number in active_reference_number_by_scene.items():
        source_key = scene_last_task_key_by_number.get(reference_number)
        target_key = scene_first_task_key_by_number.get(scene_number)
        if source_key and target_key and source_key != target_key:
            spec.add_edge(source_key, target_key)

    # --- fixed pipeline steps, matching the plan's own voiceover/music/
    # captions/branding toggles. Already-disabled steps start SKIPPED —
    # see module docstring's honesty note about why SCENE tasks have no
    # edges between each other but everything feeds VOICE. ---
    spec.add_task("voice", TaskSpec(type=ProductionTaskType.VOICE, initial_status=None if plan.voiceover.enabled else ProductionTaskStatus.SKIPPED))
    for scene_key in scene_keys:
        spec.add_edge(scene_key, "voice")

    spec.add_task("captions", TaskSpec(type=ProductionTaskType.CAPTIONS, initial_status=None if plan.captions.enabled else ProductionTaskStatus.SKIPPED))
    spec.add_edge("voice", "captions")

    spec.add_task("music", TaskSpec(type=ProductionTaskType.MUSIC, initial_status=None if (plan.music.enabled or plan.ambience.enabled) else ProductionTaskStatus.SKIPPED))
    spec.add_task("branding", TaskSpec(type=ProductionTaskType.BRANDING, initial_status=None if plan.branding.enabled else ProductionTaskStatus.SKIPPED))

    spec.add_task("render", TaskSpec(type=ProductionTaskType.RENDER))
    for key in [*scene_keys, "voice", "captions", "music", "branding"]:
        spec.add_edge(key, "render")

    budget_profile = plan.budget_profile or ("short_form" if plan.duration_seconds <= settings.short_form_max_duration_seconds else "long_form")
    max_shots = settings.short_form_max_shots if budget_profile == "short_form" else settings.long_form_max_shots
    max_retries = settings.short_form_max_retries_per_shot if budget_profile == "short_form" else settings.long_form_max_retries_per_shot
    if len(result.created_shots) > max_shots:
        raise InvalidGenerationParamsError(
            f"The {budget_profile.replace('_', ' ')} budget profile supports at most {max_shots} shots.",
            details={"created_shots": len(result.created_shots), "max_shots": max_shots, "budget_profile": budget_profile},
        )
    if next_order_index > settings.max_shots_per_project:
        raise InvalidGenerationParamsError(
            f"Project shot limit of {settings.max_shots_per_project} would be exceeded.",
            details={"project_shots_after_plan": next_order_index, "max_shots_per_project": settings.max_shots_per_project},
        )

    await dag.materialize_dag(session, spec, production_id=production.id, project_id=project.id, user_id=user_id)

    plan_record.plan_json = plan.model_dump(mode="json")
    plan_record.status = ProductionPlanStatus.APPROVED
    plan_record.approved_at = datetime.now(timezone.utc)
    production.status = ProductionStatus.APPROVED
    production.planning_status = ProductionStatus.APPROVED
    project.status = ProjectStatus.GENERATING
    await session.commit()

    estimated_credits = await _estimate_production_credits(session, production.id)
    await ProductionBudgetService(session).estimate_and_create(
        production_id=production.id, project_id=project.id, user_id=user_id, estimated_credits=estimated_credits,
        budget_profile=budget_profile, max_shots=max_shots, max_retries_per_shot=max_retries,
    )

    logger.info(
        "plan_executed", project_id=project.id, production_id=production.id,
        shots_created=len(result.created_shots), scenes_skipped=len(result.skipped_scenes),
    )
    return result


async def _estimate_production_credits(session: AsyncSession, production_id: str) -> int:
    """Sums the estimated credit cost of every SCENE task that will
    actually need a real generation submission (READY or BLOCKED — i.e.
    not already COMPLETED/SKIPPED at build time) — the same
    per-model/per-duration math routers/projects.py's /generate endpoint
    used before this pass, now computed once at approve time and stored
    on the ProductionBudget rather than recomputed at generate time."""
    from app.services.generation.pricing import estimate_reservation
    from app.services.providers.fal.catalog import get_model
    from app.services.providers.audio.pricing import estimate_audio_cost

    tasks = await dag.list_tasks_for_production(session, production_id)
    total = 0
    for task in tasks:
        if task.type != ProductionTaskType.SCENE or task.status in (ProductionTaskStatus.COMPLETED, ProductionTaskStatus.SKIPPED) or not task.shot_id:
            continue
        shot = await session.get(Shot, task.shot_id)
        if not shot or not shot.model_id:
            continue
        model = get_model(shot.model_id)
        _, credits = estimate_reservation(model, duration_seconds=shot.duration_seconds)
        total += credits
    # Reserve for audio too: the former budget only counted visual-generation tasks.
    plan_record = (await session.execute(
        select(ProductionPlanRecord).where(ProductionPlanRecord.production_id == production_id)
        .order_by(ProductionPlanRecord.version.desc()).limit(1)
    )).scalar_one_or_none()
    if plan_record and plan_record.plan_json:
        plan = ProductionPlan.model_validate(plan_record.plan_json)
        brand_music_available = False
        if plan.branding.enabled and plan.branding.brand_kit_id:
            from app.models.brand_kit import BrandKit
            brand_kit = await session.get(BrandKit, plan.branding.brand_kit_id)
            brand_music_available = bool(brand_kit and brand_kit.default_music_s3_key)
        total += estimate_audio_cost(plan, brand_music_available=brand_music_available)["estimated_credits"]
    return total


async def _route_scene(session, scene: ScenePlan, plan: ProductionPlan) -> str | None:
    capability = "image_to_video" if (
        scene.character_id or scene.product_id or scene.reference_scene_number or scene.reference_image_s3_key
        or scene.continuity_mode in ("character", "previous_final_frame", "scene_reference")
    ) else "text_to_video"

    # Honor the user's requested engine when that engine is configured. The
    # exact model is stored on the Shot during approval, so execution does not
    # silently re-decide the engine later. If it is unavailable, fall through
    # to the normal router rather than making the whole plan unusable.
    preferred_id = None
    if plan.video_engine == "wan":
        preferred_id = "wan-2.2-ti2v-5b-i2v" if capability == "image_to_video" else "wan-2.2-ti2v-5b"
    elif plan.video_engine == "kling":
        preferred_id = "kling-2.5-turbo-pro-i2v" if capability == "image_to_video" else "kling-2.5-turbo-pro"
    if preferred_id:
        preferred = MODELS.get(preferred_id)
        if preferred and preferred.get("enabled", True) and preferred.get("supports_movie_shots") and preferred["type"] == capability and provider_is_configured(preferred["provider"]):
            return preferred_id

    try:
        model = await select_model(session, RoutingRequest(capability, plan.quality_mode, require_movie_shot_support=True))
    except NoRoutableModelError:
        return None
    return model["id"]

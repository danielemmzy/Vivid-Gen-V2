"""Movie/storyboard orchestration — the 'make a movie' feature.

The core problem this solves (per the community research in the
architecture plan): AI video models generate each shot independently, so a
character's face, wardrobe, and the scene's look drift between clips. The
practical workaround creators use manually — lock a character reference
sheet once, and pass it into every shot that character appears in — is
what this service automates:

  1. Create a Character with 1+ reference images (a photo, or a generated
     turnaround sheet). `locked_version` freezes which reference set a shot
     was generated against.
  2. Create a Project with an ordered list of Shots, each shot referencing
     zero or more Characters.
  3. Submitting a shot passes the character's reference image as the
     conditioning image (image-to-video) or as an extra reference input,
     rather than letting the model invent the character fresh each time.
  4. When every shot in a project reaches `completed`, enqueue
     AssembleMovieJob to concatenate them into one final file.

This does not solve character consistency at the model level (that's a
research problem — see NVIDIA's Video Storyboarding paper) — it solves it
at the product level, the same way every competitor mentioned in the
research (ImagineArt, Storyboard Creator AI, invideo) does: pin a
reference, reuse it, let the user regenerate one shot at a time instead of
the whole project when a shot doesn't match.
"""
from uuid import uuid4
import tempfile

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import GenerationStatus, GenerationType, ProjectStatus, ShotStatus
from app.core.exceptions import (
    CharacterNotFoundError,
    InvalidGenerationParamsError,
    ProjectLimitExceededError,
    ProjectNotCancellableError,
    ProjectNotFoundError,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.models.generation import Generation
from app.models.production import Production
from app.models.product import Product
from app.models.project import Character, Project, Shot
from app.repository.projects import ProjectRepository
from app.services.credits.service import CreditService
from app.services.generation.service import GenerationService
from app.services.providers.fal.catalog import movie_shot_models

logger = get_logger(__name__)


def _to_shot_status(generation_status: str) -> str:
    """GenerationStatus and ShotStatus are different enums with different
    vocabularies (GenerationStatus has reserving_credits/postprocessing/
    refunded, which ShotStatus doesn't) — this maps rather than assumes
    they're interchangeable, used by select_shot_version."""
    if generation_status == GenerationStatus.COMPLETED:
        return ShotStatus.COMPLETED
    if generation_status in (GenerationStatus.FAILED, GenerationStatus.REFUNDED):
        return ShotStatus.FAILED
    return ShotStatus.PROCESSING


class MovieService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ProjectRepository(session)
        self.generations = GenerationService(session)
        self.credits = CreditService(session)

    async def create_project(self, user_id: str, title: str, description: str | None, aspect_ratio: str, resolution: str) -> Project:
        project = Project(id="proj_" + uuid4().hex, user_id=user_id, title=title, description=description, aspect_ratio=aspect_ratio, resolution=resolution)
        self.repo.add(project)
        await self.session.commit()
        return project

    async def create_character(self, user_id: str, project_id: str, name: str, description: str | None, reference_s3_keys: list[str], voice_id: str | None) -> Character:
        project = await self.repo.get_owned(project_id, user_id)
        if not project:
            raise ProjectNotFoundError("Project not found", details={"project_id": project_id})
        existing_count = await self.repo.count_characters(project_id)
        if existing_count >= settings.max_characters_per_project:
            raise ProjectLimitExceededError(f"Maximum {settings.max_characters_per_project} characters per project")
        character = Character(
            id="char_" + uuid4().hex, user_id=user_id, project_id=project_id, name=name, description=description,
            reference_s3_keys=reference_s3_keys, voice_id=voice_id,
        )
        self.repo.add_character(character)
        await self.session.commit()
        return character

    async def add_shot(
        self, user_id: str, project_id: str, *, prompt: str, camera_notes: str | None, duration_seconds: int,
        character_ids: list[str], model_id: str | None, scene_number: int | None = None, production_id: str | None = None,
        reference_shot_id: str | None = None, continuity_mode: str = "none", timeline_duration_seconds: float | None = None,
        product_id: str | None = None, reference_image_s3_key: str | None = None,
        order_index: int | None = None, commit: bool = True, enforce_limit: bool = True,
        project_record: Project | None = None,
    ) -> Shot:
        project = project_record or await self.repo.get_owned(project_id, user_id)
        if not project or project.id != project_id or project.user_id != user_id:
            raise ProjectNotFoundError("Project not found", details={"project_id": project_id})
        shots = await self.repo.get_shots(project_id) if order_index is None or enforce_limit else []
        if enforce_limit and len(shots) >= settings.max_shots_per_project:
            raise ProjectLimitExceededError(f"Maximum {settings.max_shots_per_project} shots per project")

        for cid in character_ids:
            if not await self.repo.get_character_owned(cid, project_id):
                raise CharacterNotFoundError("Character not found in this project", details={"character_id": cid})
        if product_id:
            product = await self.session.get(Product, product_id)
            if not product or product.project_id != project_id:
                raise InvalidGenerationParamsError("Product reference does not belong to this project.", details={"product_id": product_id})
        if reference_shot_id:
            reference_shot = await self.session.get(Shot, reference_shot_id)
            if (not reference_shot or reference_shot.project_id != project_id
                    or (production_id and reference_shot.production_id != production_id)):
                raise InvalidGenerationParamsError(
                    "Continuity references must point to a shot in the same project and production.",
                    details={"reference_shot_id": reference_shot_id, "production_id": production_id},
                )

        resolved_model = model_id or (movie_shot_models()[0]["id"] if movie_shot_models() else None)
        if not resolved_model:
            raise InvalidGenerationParamsError("No movie-capable model is available")

        shot = Shot(
            id="shot_" + uuid4().hex, project_id=project_id, production_id=production_id,
            order_index=order_index if order_index is not None else len(shots),
            prompt=prompt, camera_notes=camera_notes, duration_seconds=duration_seconds,
            character_ids=character_ids, product_id=product_id, model_id=resolved_model, scene_number=scene_number,
            reference_shot_id=reference_shot_id, continuity_mode=continuity_mode,
            reference_image_s3_key=reference_image_s3_key, timeline_duration_seconds=timeline_duration_seconds,
        )
        self.repo.add_shot(shot)
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return shot

    async def submit_shot(self, user_id: str, project_id: str, shot_id: str) -> Shot:
        """Submits one shot for generation, conditioning on its first pinned
        character's locked reference image when present — this is the
        continuity mechanism described in the module docstring."""
        shot = await self.repo.get_shot_owned(shot_id, project_id)
        if not shot:
            raise InvalidGenerationParamsError("Shot not found", details={"shot_id": shot_id})
        await self._submit_generation_for(user_id, project_id, shot)
        await self.session.commit()
        return shot

    async def regenerate_shot(self, user_id: str, project_id: str, shot_id: str, *, prompt: str | None = None) -> Shot:
        """V2 (B08 — scene versioning): creates a NEW Generation for an
        already-generated shot instead of overwriting it. The previous
        `generation_id` moves into `generation_history` — nothing is
        deleted, so credit/billing history for every past attempt stays
        intact, and `select_shot_version` can switch back to an earlier
        one later. Only allowed once the shot has actually reached a
        terminal state (completed/failed) — regenerating something still
        mid-flight would race with its own webhook completion."""
        shot = await self.repo.get_shot_owned(shot_id, project_id)
        if not shot:
            raise InvalidGenerationParamsError("Shot not found", details={"shot_id": shot_id})
        if shot.status not in (ShotStatus.COMPLETED, ShotStatus.FAILED):
            raise InvalidGenerationParamsError(
                "Can only regenerate a shot that has completed or failed",
                details={"shot_id": shot_id, "current_status": shot.status},
            )

        if shot.generation_id:
            shot.generation_history = [*shot.generation_history, shot.generation_id]
        if prompt:
            shot.prompt = prompt

        await self._submit_generation_for(user_id, project_id, shot)
        await self.session.commit()
        return shot

    async def select_shot_version(self, project_id: str, shot_id: str, generation_id: str) -> Shot:
        """Swaps which generation is the shot's active one — the currently
        active one moves into history, the requested one moves out. Only
        allows selecting a generation this shot has actually produced
        (its current one or something in its own history) — never an
        arbitrary generation_id belonging to a different shot. The shot's
        status is set from the SELECTED generation's real status, not
        assumed — selecting a version that itself failed should leave the
        shot showing as failed, not falsely completed."""
        shot = await self.repo.get_shot_owned(shot_id, project_id)
        if not shot:
            raise InvalidGenerationParamsError("Shot not found", details={"shot_id": shot_id})
        if generation_id == shot.generation_id:
            return shot
        if generation_id not in shot.generation_history:
            raise InvalidGenerationParamsError(
                "That generation is not a version of this shot", details={"shot_id": shot_id, "generation_id": generation_id},
            )

        generation = await self.session.get(Generation, generation_id)
        if not generation:
            raise InvalidGenerationParamsError("That generation no longer exists", details={"generation_id": generation_id})

        history = [g for g in shot.generation_history if g != generation_id]
        if shot.generation_id:
            history.append(shot.generation_id)
        shot.generation_history = history
        shot.generation_id = generation_id
        shot.status = _to_shot_status(generation.status)
        await self.session.commit()
        return shot

    async def _submit_generation_for(self, user_id: str, project_id: str, shot: Shot) -> None:
        """Shared by submit_shot and regenerate_shot — the actual
        character-conditioning + GenerationService.create() call. Kept in
        one place so the two entry points can never drift out of sync.

        gap-closure (0007): on synchronous submission failure (every
        retry/fallback exhausted at submission time — see
        GenerationService.create), this now calls
        orchestration/scheduler.py::on_task_completed for the SCENE task
        this shot belongs to, instead of the round-2 flat
        `production_task.mark_scene_task_for_shot` helper (deleted this
        round) — that's what lets the failure propagate to VOICE/RENDER
        through the real dependency graph rather than only updating the
        task's own row in isolation."""
        previous_generation_id = shot.generation_id
        try:
            reference_key = None
            referenced_shot = await self.session.get(Shot, shot.reference_shot_id) if shot.reference_shot_id else None
            if referenced_shot and referenced_shot.project_id != project_id:
                raise InvalidGenerationParamsError("Continuity references must stay within the same project.")
            character = None
            if shot.character_ids:
                character = await self.repo.get_character_owned(shot.character_ids[0], project_id)
            product = await self.session.get(Product, shot.product_id) if shot.product_id else None
            if product and product.project_id != project_id:
                raise InvalidGenerationParamsError("Product references must stay within the same project.")

            # Explicit scene-to-scene continuity takes precedence over static
            # character sheets. The reference frame is extracted once and cached
            # against the exact source generation by Asset Router.
            if shot.reference_image_s3_key:
                reference_key = shot.reference_image_s3_key
            elif referenced_shot:
                from app.orchestration.asset_router import resolve_reference_image
                with tempfile.TemporaryDirectory(prefix="vivid-ref-") as tmpdir:
                    reference_key = await resolve_reference_image(
                        self.session, character=character, product=product, referenced_shot=referenced_shot, tmpdir=tmpdir,
                    )
                if not reference_key:
                    raise InvalidGenerationParamsError(
                        "The preceding shot has no usable final-frame reference; retry that shot after its output is available.",
                        details={"shot_id": shot.id, "reference_shot_id": referenced_shot.id},
                    )
            elif character and character.reference_s3_keys:
                reference_key = character.reference_s3_keys[0]
            elif product and product.reference_asset_ids:
                from app.models.asset import Asset
                product_asset = await self.session.get(Asset, product.reference_asset_ids[0])
                reference_key = product_asset.s3_key if product_asset else None

            generation_type = GenerationType.IMAGE_TO_VIDEO if reference_key else GenerationType.TEXT_TO_VIDEO
            project = await self.repo.get_owned(project_id, user_id)
            requested_resolution = project.resolution if project and project.resolution in ("420p", "720p") else "720p"
            requested_aspect_ratio = project.aspect_ratio if project and project.aspect_ratio in ("16:9", "9:16", "1:1", "4:3", "3:4") else "16:9"
            response = await self.generations.create(
                user_id=user_id, generation_type=generation_type, model_id=shot.model_id, prompt=shot.prompt,
                input_s3_key=reference_key, duration_seconds=shot.duration_seconds, resolution=requested_resolution,
                aspect_ratio=requested_aspect_ratio, project_id=project_id, shot_id=shot.id, production_id=shot.production_id,
                character_id=shot.character_ids[0] if shot.character_ids else None,
            )
        except Exception as exc:
            shot.status = ShotStatus.FAILED
            if hasattr(exc, "generation_id"):
                failed_generation_id = exc.generation_id
                if previous_generation_id and previous_generation_id != failed_generation_id and previous_generation_id not in shot.generation_history:
                    shot.generation_history = [*shot.generation_history, previous_generation_id]
                shot.generation_id = failed_generation_id
            await self.session.commit()
            from app.core.constants import ProductionTaskStatus
            from app.orchestration import dag, scheduler
            task = await dag.get_task_for_shot(self.session, shot.id)
            # Guard against regenerate_shot being called on a shot whose
            # SCENE task already completed successfully once (e.g. the
            # whole production already rendered, and the user is
            # regenerating just this shot afterward) — that task must
            # NOT be retroactively failed; only a task that hasn't
            # already succeeded should have this failure propagated.
            if task and task.status != ProductionTaskStatus.COMPLETED:
                task.status = ProductionTaskStatus.FAILED
                task.error = "Generation submission failed after exhausting retries/fallbacks"
                await self.session.commit()
                await scheduler.on_task_completed(self.session, task.id, success=False, error=task.error)
            raise
        if previous_generation_id and previous_generation_id != response.id and previous_generation_id not in shot.generation_history:
            shot.generation_history = [*shot.generation_history, previous_generation_id]
        shot.generation_id = response.id
        shot.status = ShotStatus.PROCESSING

    async def add_user_asset_shot(
        self, user_id: str, project_id: str, *, s3_key: str, prompt: str,
        camera_notes: str | None, duration_seconds: int, scene_number: int | None = None, production_id: str | None = None,
        order_index: int | None = None, commit: bool = True, enforce_limit: bool = True,
        project_record: Project | None = None,
    ) -> Shot:
        """gap-closure: minimal Asset Router (P0.5 in the audit) — a scene
        whose plan.visual_type is "user_asset" doesn't need a generation
        at all, it needs the Shot pipeline (Shot -> Generation -> the
        render manifest) to treat an already-uploaded asset as though it
        were one. Rather than inventing a second, parallel "Shot with no
        Generation" code path, this creates a real Generation row that's
        already COMPLETED, reserves/charges zero credits, and has no
        provider_request_id — a pass-through, not a fake generation. A
        late webhook can never touch it (there's no provider_request_id
        to match)."""
        project = project_record or await self.repo.get_owned(project_id, user_id)
        if not project or project.id != project_id or project.user_id != user_id:
            raise ProjectNotFoundError("Project not found", details={"project_id": project_id})
        shots = await self.repo.get_shots(project_id) if order_index is None or enforce_limit else []
        if enforce_limit and len(shots) >= settings.max_shots_per_project:
            raise ProjectLimitExceededError(f"Maximum {settings.max_shots_per_project} shots per project")

        from uuid import uuid4
        from datetime import datetime, timezone

        generation_id = "gen_" + uuid4().hex
        generation = Generation(
            id=generation_id, user_id=user_id, type=GenerationType.MOVIE_SHOT, status=GenerationStatus.COMPLETED,
            model_id="user-asset-passthrough", output_s3_key=s3_key, duration_seconds=duration_seconds,
            estimated_provider_cost_usd=0, credits_reserved=0, credits_charged=0,
            project_id=project_id, production_id=production_id, started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
            metadata_json={"source": "user_asset", "note": "pass-through of an existing upload, not a generation"},
        )
        self.session.add(generation)

        shot = Shot(
            id="shot_" + uuid4().hex, project_id=project_id, production_id=production_id,
            order_index=order_index if order_index is not None else len(shots),
            prompt=prompt, camera_notes=camera_notes, duration_seconds=duration_seconds,
            character_ids=[], model_id=None, generation_id=generation_id, status=ShotStatus.COMPLETED,
            scene_number=scene_number,
        )
        self.repo.add_shot(shot)
        await self.session.flush()
        generation.shot_id = shot.id
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return shot

    async def cancel_project(self, user_id: str, project_id: str) -> Project:
        """gap-closure: there was previously no way to cancel a project
        anywhere in the API — ProjectStatus.CANCELLED was a legal
        state-machine transition that nothing ever produced. Cancels every
        still-refundable Generation belonging to this project's shots
        (skips ones that are already terminal — a shot that already
        completed keeps its charge, it isn't retroactively refunded) and
        marks the project CANCELLED. Does not attempt to cancel the
        provider-side request (no provider in this codebase exposes a
        cancel API) — a late webhook for a cancelled generation is a
        no-op, per GenerationStatus.CANCELLED being terminal.

        gap-closure (0007): now ALSO propagates cancellation through the
        DAG (orchestration/scheduler.py::cancel_production) — every
        non-terminal ProductionTask is marked failed/cancelled so no
        downstream task (e.g. RENDER, still waiting on other scenes) can
        ever become READY after this call, not just the Shots/
        Generations themselves."""
        project = await self.repo.get_owned(project_id, user_id)
        if not project:
            raise ProjectNotFoundError("Project not found", details={"project_id": project_id})
        if project.status in (ProjectStatus.READY, ProjectStatus.CANCELLED, ProjectStatus.FAILED):
            raise ProjectNotCancellableError(
                "This project has already finished and can no longer be cancelled",
                details={"project_id": project_id, "status": project.status},
            )

        shots = await self.repo.get_shots(project_id)
        for shot in shots:
            if shot.generation_id and shot.status in (ShotStatus.PENDING, ShotStatus.QUEUED, ShotStatus.PROCESSING):
                try:
                    await self.generations.cancel(shot.generation_id, user_id)
                except Exception:  # noqa: BLE001 - already-terminal generation, not a reason to abort the project cancel
                    pass
                shot.status = ShotStatus.FAILED

        if project.current_production_id:
            from app.orchestration.scheduler import cancel_production
            await cancel_production(self.session, project.current_production_id)
            production = await self.session.get(Production, project.current_production_id)
            if production:
                from datetime import datetime, timezone
                from app.core.constants import ProductionStatus
                production.status = ProductionStatus.CANCELLED
                production.execution_status = ProductionStatus.CANCELLED
                production.cancelled_at = datetime.now(timezone.utc)

        project.status = ProjectStatus.CANCELLED
        await self.session.commit()
        logger.info("project_cancelled", project_id=project_id, user_id=user_id)
        return project

"""gap-closure: Plan Validator (P0.3 in the audit's priority list).

Before this, nothing stood between "the Director produced a plan" and
"the user can approve it" — Pydantic's own field constraints on
ProductionPlan (duration bounds, scene count bounds) are schema
validation, not plan validation: they don't check whether a referenced
character/brand_kit actually exists and is owned by this user, and they
don't check whether the *executable* scenes (see executor.py's
`is_scene_executable`) still add up to something close to the plan's
stated duration — a plan that's 70% stock_video scenes with no
stock_source_url was silently approvable before this, producing a much
shorter final video than the user was shown.

This does not try to validate everything the full canonical spec's
Plan Validator would (provider-level capability negotiation, a full
cost estimate — that's credit_preflight.py in routers/projects.py) — it
validates what's actually knowable and enforceable from the plan +
this user's own rows: referenced characters/brand kits exist, and the
plan's promised duration isn't mostly going to be silently dropped.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

from app.orchestration.executor import is_scene_executable
from app.orchestration.production_plan import ProductionPlan
from app.models.product import Product
from app.models.asset import Asset
from app.repository.brand_kits import BrandKitRepository
from app.repository.projects import ProjectRepository
from app.services.entitlements import get_user_entitlement

async def validate_plan(session: AsyncSession, user_id: str, project_id: str, plan: ProductionPlan) -> list[str]:
    """Returns a list of human-readable validation errors — empty means
    the plan may be approved. Never raises; the caller (routers/projects.py)
    decides whether to raise PlanValidationError with the full list."""
    errors: list[str] = []

    if not plan.scenes:
        errors.append("Plan has no scenes.")
        return errors

    project_repo = ProjectRepository(session)
    entitlement = await get_user_entitlement(session, user_id)
    brand_kit = None
    if plan.branding.enabled and "brand_kits" not in entitlement.get("features", []):
        errors.append(f"Brand kits are not included in your {entitlement['label']} plan.")
    if plan.voiceover.reference_audio_s3_key and "voice_cloning" not in entitlement.get("features", []):
        errors.append(f"Voice cloning is not included in your {entitlement['label']} plan; remove the reference sample or request a plan change.")

    referenced_character_ids = {s.character_id for s in plan.scenes if s.character_id}
    if referenced_character_ids:
        owned_characters = await project_repo.list_characters(project_id)
        character_by_id = {c.id: c for c in owned_characters}
        for cid in sorted(referenced_character_ids - set(character_by_id)):
            errors.append(f"Scene references character_id '{cid}', which does not exist on this project.")
        for cid in sorted(referenced_character_ids & set(character_by_id)):
            if not character_by_id[cid].reference_s3_keys:
                errors.append(f"Character '{cid}' has no reference image; add one or remove the character reference from the scene.")

    for product_id in sorted({s.product_id for s in plan.scenes if s.product_id}):
        product = await session.get(Product, product_id)
        if not product or product.project_id != project_id:
            errors.append(f"Scene references product_id '{product_id}', which does not exist on this project.")
        elif not product.reference_asset_ids:
            errors.append(f"Product '{product_id}' has no reference image asset.")
        else:
            for asset_id in product.reference_asset_ids:
                asset = await session.get(Asset, asset_id)
                if not asset or asset.project_id != project_id:
                    errors.append(f"Product '{product_id}' references missing or out-of-project asset '{asset_id}'.")

    if plan.branding.enabled and plan.branding.brand_kit_id:
        brand_kit = await BrandKitRepository(session).get_owned(plan.branding.brand_kit_id, user_id)
        if not brand_kit:
            errors.append(f"branding.brand_kit_id '{plan.branding.brand_kit_id}' does not exist or is not owned by this user.")

    if plan.voiceover.enabled:
        tts_provider = plan.voiceover.provider or settings.tts_provider
        if tts_provider == "chatterbox" and not settings.chatterbox_tts_base_url.strip():
            errors.append("Self-hosted Chatterbox is selected for narration but CHATTERBOX_TTS_BASE_URL is not configured on the backend.")
        elif tts_provider == "fal_chatterbox" and not settings.fal_key:
            errors.append("Hosted Chatterbox is selected for narration but FAL_KEY is not configured on the backend.")
        elif tts_provider == "elevenlabs" and not settings.elevenlabs_api_key:
            errors.append("ElevenLabs is selected for narration but ELEVENLABS_API_KEY is not configured on the backend.")
        elif tts_provider == "fal" and not settings.fal_key:
            errors.append("Fal TTS is selected for narration but FAL_KEY is not configured on the backend.")

    reference_key = plan.voiceover.reference_audio_s3_key
    if reference_key:
        # Keys are issued by POST /uploads/presign with purpose=voice-reference.
        # Never accept another user's key or arbitrary URLs from a plan payload.
        expected_prefix = f"{settings.s3_input_prefix.rstrip('/')}/{user_id}/voice-reference/"
        if not reference_key.startswith(expected_prefix) or ".." in reference_key.split("/"):
            errors.append("Voice reference must be an uploaded audio sample owned by this user.")

    if reference_key and (plan.voiceover.provider or settings.tts_provider) not in {"fal_chatterbox"}:
        errors.append("Recorded/reference voice cloning currently requires the hosted Chatterbox provider; select it or remove the reference sample.")

    has_brand_music = bool(brand_kit and brand_kit.default_music_s3_key)
    if plan.music.enabled and not has_brand_music:
        music_provider = plan.music.provider or settings.audio_generation_provider
        if music_provider == "fal" and not settings.fal_key:
            errors.append("Music generation is enabled but FAL_KEY is not configured on the backend, and no brand-kit music track is available.")
    if plan.ambience.enabled:
        ambience_provider = plan.ambience.provider or settings.audio_generation_provider
        if ambience_provider == "fal" and not settings.fal_key:
            errors.append("Ambience generation is enabled but FAL_KEY is not configured on the backend.")

    allowed_reference_prefixes = (
        f"{settings.s3_input_prefix.rstrip('/')}/{user_id}/url-reference/",
        f"{settings.s3_input_prefix.rstrip('/')}/{user_id}/ppt-reference/",
        f"{settings.s3_input_prefix.rstrip('/')}/{user_id}/media-reference/",
    )
    for scene in plan.scenes:
        key = scene.reference_image_s3_key
        if key and (not key.startswith(allowed_reference_prefixes) or ".." in key.split("/")):
            errors.append(f"Scene {scene.scene_number} reference image must be imported into this user's Vivid-Gen media storage.")
        asset_key = scene.source_asset_s3_key
        allowed_asset_prefix = f"{settings.s3_input_prefix.rstrip('/')}/{user_id}/"
        if asset_key and (not asset_key.startswith(allowed_asset_prefix) or ".." in asset_key.split("/")):
            errors.append(f"Scene {scene.scene_number} source asset must be an upload owned by this user.")

    scene_numbers = [s.scene_number for s in plan.scenes]
    if len(scene_numbers) != len(set(scene_numbers)):
        errors.append("Scene numbers are not unique.")

    executable_seconds = sum(s.duration_seconds for s in plan.scenes if is_scene_executable(s))
    total_seconds = plan.total_scene_seconds()
    if total_seconds != plan.duration_seconds:
        errors.append(
            f"Scene timeline totals {total_seconds}s but the requested finished duration is {plan.duration_seconds}s. "
            "Adjust scene durations so the assembled timeline matches the requested movie length."
        )
    if plan.voiceover.enabled and not any((scene.voiceover_line or "").strip() for scene in plan.scenes):
        errors.append("Narration is enabled but no scene has a voiceover_line. Add narration text or disable narration before approval.")
    for label, audio_plan in (("music", plan.music), ("ambience", plan.ambience)):
        if audio_plan.enabled:
            if audio_plan.start_seconds >= plan.duration_seconds:
                errors.append(f"{label}.start_seconds must be earlier than the finished movie duration.")
            if audio_plan.duration_seconds is not None and audio_plan.duration_seconds <= 0:
                errors.append(f"{label}.duration_seconds must be positive when provided.")
    if executable_seconds != total_seconds:
        errors.append(
            f"Only {executable_seconds}s of the {total_seconds}s timeline is executable. "
            "Every scene must have a supported visual source before production can start."
        )
    by_number = {scene.scene_number: scene for scene in plan.scenes}
    ordered_numbers = sorted(by_number)
    previous_number = {ordered_numbers[i]: ordered_numbers[i - 1] for i in range(1, len(ordered_numbers))}
    for scene in plan.scenes:
        if scene.continuity_mode != "none" and scene.visual_type != "generated_video":
            errors.append(f"Scene {scene.scene_number} requests video continuity but its visual_type is '{scene.visual_type}'.")
        reference_number = scene.reference_scene_number
        if reference_number is None and scene.continuity_mode == "previous_final_frame":
            reference_number = previous_number.get(scene.scene_number)
            if reference_number is None:
                errors.append(f"Scene {scene.scene_number} requests previous_final_frame continuity but has no previous scene.")
        if scene.continuity_mode == "scene_reference" and reference_number is None:
            errors.append(f"Scene {scene.scene_number} uses scene_reference continuity but does not specify reference_scene_number.")
        if reference_number is not None:
            referenced = by_number.get(reference_number)
            if not referenced:
                errors.append(f"Scene {scene.scene_number} references missing scene {reference_number}.")
            elif reference_number >= scene.scene_number:
                errors.append(f"Scene {scene.scene_number} must reference an earlier scene, not scene {reference_number}.")
            elif referenced.visual_type != "generated_video":
                errors.append(f"Scene {scene.scene_number} can only use a generated_video scene as a final-frame reference; scene {reference_number} is '{referenced.visual_type}'.")
        if scene.continuity_mode == "character" and not scene.character_id:
            errors.append(f"Scene {scene.scene_number} requests character continuity but has no character_id.")

    if plan.budget_profile == "short_form" and plan.duration_seconds > 60:
        errors.append("The short_form budget profile supports a maximum finished duration of 60 seconds; choose long_form for longer movies.")
    if plan.duration_seconds > 600:
        errors.append("Finished duration exceeds the configured long-form limit of 600 seconds.")

    for scene in plan.scenes:
        if scene.visual_type == "user_asset" and not scene.source_asset_s3_key:
            errors.append(f"Scene {scene.scene_number} has visual_type 'user_asset' but no source_asset_s3_key.")
        if scene.visual_type == "stock_video" and not scene.stock_source_url:
            errors.append(f"Scene {scene.scene_number} has a stock_video source but no selected/imported clip URL.")

    return errors

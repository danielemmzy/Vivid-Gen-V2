"""V2 workflow presets (spec §31, §64). Every route here either:
  (a) builds a workflow-specific prompt/source_facts and hands it to the
      SAME planner.create_production_plan + executor.create_production_for_plan
      path used by ads, product-video, youtube, url-to-video, podcast and presentation, or
  (b) runs the Shorts/Repurpose footage-selection pipeline (not the
      Director), or
  (c) for dubbing, submits directly to the existing, already-working
      /generations/video-translation service call — see
      workflows/dubbing.py's module docstring for why that's a deliberate
      reuse decision, not a missing feature.

No route here contains generation logic of its own — if you're adding a
10th workflow and find yourself writing a new provider call, that
generation logic belongs in services/generation/ or a provider, not here.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import GenerationType, ProjectStatus
from app.dependencies import current_user_id, db_session
from app.orchestration import executor
from app.orchestration.planner import create_production_plan
from app.services.generation.service import GenerationService
from app.services.movie.service import MovieService
from app.workflows import ads, dubbing, podcast, presentation, product_video, url_to_video, youtube
from app.workflows.repurpose import RepurposeRequest, repurpose_as_shorts
from app.workflows.shorts import ShortsRequest, generate_shorts

router = APIRouter(prefix="/workflows", tags=["workflows"])


async def _plan_and_store(session: AsyncSession, user_id: str, title: str, plan_inputs: dict) -> dict:
    movie = MovieService(session)
    reference_keys = plan_inputs.pop("reference_image_s3_keys", [])
    source_url = plan_inputs.pop("source_url", None)
    source_pptx_s3_key = plan_inputs.pop("source_pptx_s3_key", None)
    project = await movie.create_project(user_id, title, None, "16:9", "1080p")
    project.status = ProjectStatus.PLANNING
    await session.commit()
    try:
        plan = await create_production_plan(**plan_inputs)
        if reference_keys:
            from app.workflows.planning import attach_source_visual_references
            plan = attach_source_visual_references(plan, reference_keys, source_url=source_url, source_pptx_s3_key=source_pptx_s3_key)
        director_input = {"workflow_title": title}
        if source_url:
            director_input["source_url"] = source_url
        if source_pptx_s3_key:
            director_input["source_pptx_s3_key"] = source_pptx_s3_key
        production = await executor.create_production_for_plan(
            session, user_id, project, plan, director_input=director_input,
        )
    except Exception as exc:
        await session.rollback()
        project.status = ProjectStatus.FAILED
        project.error_message = f"Planning failed: {type(exc).__name__}. Retry the workflow after checking source/provider configuration."
        await session.commit()
        raise
    return {"project_id": project.id, "production_id": production.id, "status": project.status,
            "production_plan": plan.model_dump(mode="json"),
            "source_visual_references": len(reference_keys)}


@router.post("/ads")
async def ads_workflow(body: ads.AdStudioRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    return await _plan_and_store(session, user_id, f"Ad — {body.product_name}", ads.build_plan_inputs(body))


@router.post("/product-video")
async def product_video_workflow(body: product_video.ProductVideoRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    return await _plan_and_store(session, user_id, f"Product video — {body.product_name}", product_video.build_plan_inputs(body))


@router.post("/youtube")
async def youtube_workflow(body: youtube.YouTubeRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    return await _plan_and_store(session, user_id, body.topic[:200], youtube.build_plan_inputs(body))


@router.post("/url-to-video")
async def url_to_video_workflow(body: url_to_video.UrlToVideoRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    from app.monitoring.metrics import source_extraction_total
    try:
        plan_inputs = await url_to_video.build_plan_inputs(body, user_id=user_id)
    except Exception:
        source_extraction_total.labels("url", "failed").inc()
        raise
    source_extraction_total.labels("url", "success").inc()
    return await _plan_and_store(session, user_id, f"From URL — {body.url[:150]}", plan_inputs)


@router.post("/url-to-video/preview")
async def url_to_video_preview(body: url_to_video.UrlToVideoPreviewRequest, user_id: str = Depends(current_user_id)):
    """Read a URL without importing assets, so the user can review its source."""
    from app.monitoring.metrics import source_extraction_total
    try:
        preview = await url_to_video.preview_article(body.url)
    except Exception:
        source_extraction_total.labels("url_preview", "failed").inc()
        raise
    source_extraction_total.labels("url_preview", "success").inc()
    return preview


@router.post("/podcast")
async def podcast_workflow(body: podcast.PodcastRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    plan_inputs = await podcast.build_plan_inputs(body)
    return await _plan_and_store(session, user_id, "Podcast video", plan_inputs)


@router.post("/presentation")
async def presentation_workflow(body: presentation.PresentationRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    from app.monitoring.metrics import source_extraction_total
    try:
        plan_inputs = await presentation.build_plan_inputs(body, user_id=user_id)
    except Exception:
        source_extraction_total.labels("pptx", "failed").inc()
        raise
    source_extraction_total.labels("pptx", "success").inc()
    return await _plan_and_store(session, user_id, "Presentation video", plan_inputs)


@router.post("/shorts")
async def shorts_workflow(body: ShortsRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    movie = MovieService(session)
    project = await movie.create_project(user_id, "Shorts", None, "9:16", "1080p")
    assets = await generate_shorts(session, user_id, project.id, body)
    return {"project_id": project.id, "clips": [{"id": a.id, "s3_key": a.s3_key, "duration_seconds": float(a.duration_seconds), "metadata": a.asset_metadata} for a in assets]}


@router.post("/repurpose/{project_id}")
async def repurpose_workflow(project_id: str, body: RepurposeRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    project = await MovieService(session).repo.get_owned(project_id, user_id)
    if not project:
        from app.core.exceptions import ProjectNotFoundError
        raise ProjectNotFoundError("Project not found", details={"project_id": project_id})
    assets = await repurpose_as_shorts(session, user_id, project, body)
    return {"project_id": project.id, "clips": [{"id": a.id, "s3_key": a.s3_key, "duration_seconds": float(a.duration_seconds), "metadata": a.asset_metadata} for a in assets]}


@router.post("/dubbing")
async def dubbing_workflow(body: dubbing.DubbingRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """Unlike the others, this submits directly — see workflows/dubbing.py
    for why it deliberately reuses the existing video-translation service
    call rather than building a new pipeline."""
    model = "video-translate-dub" if body.lip_sync else "video-dub-audio-only"
    return await GenerationService(session).create(
        user_id=user_id, generation_type=GenerationType.VIDEO_TRANSLATION, model_id=model,
        input_s3_key=body.source_video_s3_key, target_language=body.target_language,
    )

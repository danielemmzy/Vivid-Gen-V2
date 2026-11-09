"""Shared workflow-plan enrichment used by every creation route."""
from app.orchestration.production_plan import ProductionPlan


def attach_source_visual_references(
    plan: ProductionPlan,
    reference_keys: list[str],
    *,
    source_url: str | None = None,
    source_pptx_s3_key: str | None = None,
) -> ProductionPlan:
    """Attach imported source images as real per-scene conditioning references.

    This is deliberately plan-level so URL, PPTX and future source workflows
    still enter the same editable storyboard and approval path.
    """
    if not reference_keys:
        return plan
    source_provider = "article" if source_url else "presentation" if source_pptx_s3_key else "imported_media"
    attribution = source_url or ("Embedded image extracted from the uploaded presentation" if source_pptx_s3_key else "Imported source media")
    license_note = "unverified external source — confirm permission before rendering" if source_url else "user-provided deck — rights not verified" if source_pptx_s3_key else "source license not verified"
    scenes = list(plan.scenes)
    for index, key in enumerate(reference_keys[:len(scenes)]):
        scenes[index] = scenes[index].model_copy(update={
            "reference_image_s3_key": key,
            "source_provider": source_provider,
            "source_attribution": attribution,
            "source_license": license_note,
        })
    return plan.model_copy(update={"scenes": scenes})

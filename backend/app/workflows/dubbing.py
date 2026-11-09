"""V2 Phase 21 (spec §45): Dubbing.

Deliberate decision, not an oversight: this does NOT build a new
decomposed ASR->translation->TTS->lip-sync pipeline. The existing
`video-translate-dub` fal model (already wired end-to-end via
POST /generations/video-translation with lip_sync=true — see the Phase 0
audit, this was tested working with the fake provider this session)
already does exactly what spec §45's pipeline diagram describes, as one
atomic provider call, and per this whole plan's own top rule ("if the
repository already has an equivalent implementation, reuse it, don't
create a second competing one") that existing endpoint IS the dubbing
feature. Building a from-scratch decomposed version would need a
dedicated lip-sync-only provider this codebase doesn't have (the only
lip-sync capable model in the catalog, omnihuman-1.5, does still-photo ->
lip-synced avatar, not existing-video -> re-synced mouth) — so a
DIY version today would produce translated narration with a mismatched
mouth, strictly worse than the existing all-in-one endpoint.

What this module actually adds: a thin, honest wrapper that tells the
caller to use the existing endpoint, so "dubbing" has a discoverable
workflow entry point (matching the other 8 workflows' shape) without
pretending there's new generation logic underneath it.
"""
from pydantic import BaseModel, Field


class DubbingRequest(BaseModel):
    source_video_s3_key: str
    target_language: str = Field(min_length=2, max_length=10)
    lip_sync: bool = True


def resolve(body: DubbingRequest) -> dict:
    """Returns the exact request shape for the existing, already-working
    endpoint — callers should POST this to /generations/video-translation
    rather than this module doing it, so the credit reservation/webhook/
    frontend polling flow stays exactly the one already tested this
    session, with no second code path to keep in sync."""
    return {
        "endpoint": "/generations/video-translation",
        "body": {
            "sourceVideoS3Key": body.source_video_s3_key,
            "targetLanguage": body.target_language,
            "lipSync": body.lip_sync,
        },
    }

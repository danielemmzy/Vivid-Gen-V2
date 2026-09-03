"""The provider interface. GenerationService only ever talks to this
Protocol — never to fal_client, never to a provider-specific SDK. Swapping
or adding a provider (a second video model vendor, a TTS vendor, etc.)
means writing a new class that satisfies this Protocol and registering it
in providers/registry.py; nothing in services/generation/ changes."""
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderSubmission:
    """What a provider returns immediately after accepting a job."""
    provider_request_id: str
    raw: dict[str, Any]


class GenerationProvider(Protocol):
    name: str

    async def submit_text_to_image(self, provider_model_id: str, prompt: str, **kwargs: Any) -> ProviderSubmission: ...

    async def submit_image_to_image(self, provider_model_id: str, prompt: str, image_url: str, **kwargs: Any) -> ProviderSubmission: ...

    async def submit_text_to_video(self, provider_model_id: str, prompt: str, **kwargs: Any) -> ProviderSubmission: ...

    async def submit_image_to_video(self, provider_model_id: str, prompt: str, image_url: str, **kwargs: Any) -> ProviderSubmission: ...

    async def submit_avatar(self, provider_model_id: str, image_url: str, audio_url: str, **kwargs: Any) -> ProviderSubmission: ...

    async def submit_video_translation(self, provider_model_id: str, video_url: str, target_language: str, **kwargs: Any) -> ProviderSubmission: ...

    async def submit_audio_replace(self, provider_model_id: str, video_url: str, audio_url: str, **kwargs: Any) -> ProviderSubmission: ...

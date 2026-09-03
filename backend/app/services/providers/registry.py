"""Resolve a provider name -> GenerationProvider instance. Today there are
two: fal.ai (real, costs money) and fake (zero-cost, for local dev/tests —
see providers/fake/client.py). Adding a real second paid provider means
writing a new class that satisfies the Protocol and registering it here;
nothing in services/generation/ changes.

Providers are constructed lazily so that running in `fake` mode never
requires FAL_KEY to be set at all — instantiating FalProvider eagerly
would defeat the point of a zero-cost local dev mode.
"""
from app.core.config import settings
from app.services.providers.base import GenerationProvider

_instances: dict[str, GenerationProvider] = {}


def get_provider(name: str | None = None) -> GenerationProvider:
    resolved = name or settings.generation_provider
    if resolved not in _instances:
        if resolved == "fake":
            if settings.app_env == "production":
                raise RuntimeError("GENERATION_PROVIDER=fake must never be used with APP_ENV=production")
            from app.services.providers.fake.client import fake_provider
            _instances["fake"] = fake_provider
        elif resolved == "fal":
            from app.services.providers.fal.client import FalProvider
            _instances["fal"] = FalProvider()
        else:
            raise ValueError(f"Unknown provider: {resolved}")
    return _instances[resolved]

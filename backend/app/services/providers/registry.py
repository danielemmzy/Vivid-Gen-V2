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


def provider_is_configured(name: str) -> bool:
    """Return whether a provider has the credentials needed to run jobs.

    This check is deliberately side-effect free so model routing can exclude
    unavailable providers before credits are reserved. It does not prove that
    remote credentials are valid or that a provider is healthy.
    """
    if name == "fake":
        return settings.app_env != "production"
    if name == "fal":
        return bool(settings.fal_key)
    if name == "modal":
        return all((
            settings.modal_token_id,
            settings.modal_token_secret,
            settings.modal_webhook_secret,
            settings.aws_access_key_id,
            settings.aws_secret_access_key,
            settings.aws_s3_bucket_name,
        ))
    return False


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
        elif resolved == "modal":
            from app.services.providers.modal.client import ModalProvider
            _instances["modal"] = ModalProvider()
        else:
            raise ValueError(f"Unknown provider: {resolved}")
    return _instances[resolved]

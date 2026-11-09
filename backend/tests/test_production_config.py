import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _base(**overrides):
    values = {
        "app_env": "production",
        "environment": "production",
        "backend_public_url": "https://api.example.test",
        "cors_allow_origins": ["https://app.example.test"],
        "internal_api_secret": "x" * 64,
        "database_url": "postgresql+asyncpg://postgres:postgres@localhost/db",
        "aws_region": "us-east-1",
        "aws_access_key_id": "configured",
        "aws_secret_access_key": "configured",
        "aws_s3_bucket_name": "private-bucket",
        "metrics_token": "metrics-token",
        "fal_key": "configured",
        "fal_webhook_url": "https://api.example.test/api/v1/webhooks/fal",
    }
    values.update(overrides)
    return values


def test_production_config_accepts_complete_fail_closed_values():
    settings = Settings(**_base())
    assert settings.app_env == "production"


@pytest.mark.parametrize(
    "override",
    [
        {"metrics_token": ""},
        {"backend_public_url": "http://localhost:8001"},
        {"fal_webhook_url": "http://localhost:8001/api/v1/webhooks/fal"},
        {"cors_allow_origins": ["http://localhost:3001"]},
    ],
)
def test_production_config_rejects_unsafe_defaults(override):
    with pytest.raises(ValidationError, match="Unsafe production configuration"):
        Settings(**_base(**override))

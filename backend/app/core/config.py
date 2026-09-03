from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "Vivid Gen API"
    api_prefix: str = "/api/v1"
    backend_public_url: str
    cors_allow_origins: list[str] = []

    # Internal service-to-service auth (Next.js -> FastAPI)
    internal_api_secret: str
    internal_auth_tolerance_seconds: int = 300

    # Postgres — this service owns the `core` schema only. Auth/billing tables
    # live in the `auth` schema, written exclusively by the Next.js/Prisma side.
    database_url: str
    database_schema: str = "core"
    database_pool_size: int = 10
    database_max_overflow: int = 10

    # fal.ai provider
    generation_provider: str = "fal"  # "fal" | "fake" — see services/providers/registry.py
    fal_key: str = ""
    fal_webhook_url: str = ""
    fal_webhook_tolerance_seconds: int = 300

    # Object storage
    aws_region: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_s3_bucket_name: str
    s3_presigned_ttl_seconds: int = 900
    s3_output_prefix: str = "generations"
    s3_input_prefix: str = "uploads"
    cdn_base_url: str | None = None
    cloudfront_key_pair_id: str | None = None
    cloudfront_private_key_path: str | None = None

    # Redis — queue, cache, rate limiting, idempotency locks
    redis_url: str = "redis://localhost:6379/0"

    # Credits / pricing
    credit_usd_value: float = 0.01
    generation_markup_multiplier: float = 2.5
    min_generation_credits: int = 1
    free_tier_grant_credits: int = 150

    # Limits & abuse prevention
    max_prompt_length: int = 5000
    max_video_duration_seconds: int = 60
    max_upload_bytes: int = 200 * 1024 * 1024
    rate_limit_per_minute: int = 30
    rate_limit_burst: int = 10
    rate_limit_per_ip_per_minute: int = 120
    max_concurrent_generations_per_user: int = 3
    generations_enabled: bool = True  # global kill switch — see dependencies.require_generations_enabled

    # Endpoints that fail CLOSED (503) rather than open when Redis is
    # unreachable — see middleware/rate_limit.py's module docstring.
    rate_limit_fail_closed_prefixes: list[str] = ["/generations", "/projects"]

    # Endpoint-specific overrides (requests/minute), keyed by route path suffix
    endpoint_rate_limits: dict[str, int] = {
        "/uploads/presign": 20,
        "/generations": 20,
        "/projects": 10,
    }

    # Movie / storyboard feature
    max_shots_per_project: int = 40
    max_characters_per_project: int = 12
    movie_assembly_max_seconds: int = 900

    # Content moderation
    moderation_enabled: bool = True
    moderation_blocklist_path: str | None = None

    # Observability
    log_level: str = "INFO"
    log_json: bool = True
    sentry_dsn: str | None = None
    environment: str = "development"
    metrics_token: str | None = None  # required header value to access /metrics when app_env=="production"

    # Redis cache TTLs
    model_catalog_cache_ttl_seconds: int = 300

    # Media tooling
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"

    # Scheduler
    stuck_generation_minutes: int = 30
    reconciliation_interval_seconds: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

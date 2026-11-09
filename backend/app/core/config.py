from functools import lru_cache
from pydantic import Field, model_validator
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
    # Default retail markup. Individual catalog models may override this with
    # `retail_multiplier`; keep this as the safe fallback for legacy rows.
    generation_markup_multiplier: float = 2.5
    min_generation_credits: int = 1
    free_tier_grant_credits: int = 150
    # Modal runtime-cost estimate inputs. GPU price is the published L40S
    # snapshot (2026-10); update after checking `modal billing rates`. The
    # runtime/output ratio comes from the observed ~427s worker run for a 5s
    # clip and is deliberately conservative, not an invoice reconciliation.
    modal_l40s_gpu_usd_per_second: float = 0.000542
    modal_cpu_usd_per_core_second: float = 0.0000131
    modal_memory_usd_per_gib_second: float = 0.00000222
    modal_estimated_cpu_cores: float = 1.0
    modal_estimated_memory_gib: float = 4.0
    modal_runtime_seconds_per_output_second: float = 85.4
    modal_cost_safety_factor: float = 1.25
    modal_cost_rate_version: str = "modal-public-rates-2026-10"
    # Avatar duration is not known from the current request schema; reserve
    # against this conservative estimate and reconcile against probed output.
    avatar_reservation_seconds: int = 180
    unknown_media_reservation_seconds: int = 300

    # Limits & abuse prevention
    max_prompt_length: int = 5000
    max_video_duration_seconds: int = 60
    max_upload_bytes: int = 200 * 1024 * 1024
    rate_limit_per_minute: int = 30
    rate_limit_burst: int = 10
    rate_limit_per_ip_per_minute: int = 120
    max_concurrent_generations_per_user: int = 3
    generations_enabled: bool = True  # global kill switch — see dependencies.require_generations_enabled

    # gap-closure: retry/fallback. Total attempts across the original model
    # + fallbacks, both for a synchronous submission-time failure (handled
    # inline in GenerationService.create) and an async provider-reported
    # failure (handled in GenerationService.handle_provider_error, called
    # from the fal webhook). See orchestration/provider_errors.py.
    max_generation_retry_attempts: int = 3

    # gap-closure: upload content-type hardening. Only these are accepted
    # by POST /uploads/presign — anything else is rejected before a
    # presigned PUT URL is even issued, closing the "client controls
    # content_type/extension unchecked" gap. Covers every upload the
    # frontend actually performs (see grep of `accept=` across
    # src/components/create/*.tsx and brand-kits-list.tsx) — most forms
    # use a `video/*`/`audio/*`/`image/*` browser picker, which can report
    # several concrete MIME types depending on the source file, so this is
    # deliberately a little broader than the single-type minimum rather
    # than an allowlist that silently breaks real uploads; it still
    # excludes anything executable/script-like.
    allowed_upload_content_types: list[str] = [
        "image/png", "image/jpeg", "image/webp", "image/gif",
        "video/mp4", "video/quicktime", "video/webm", "video/x-matroska", "video/x-msvideo",
        "audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/x-m4a", "audio/ogg",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx — create/presentation
    ]

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
    max_shots_per_project: int = 160
    short_form_max_duration_seconds: int = 60
    long_form_max_duration_seconds: int = 600
    short_form_max_shots: int = 20
    long_form_max_shots: int = 160
    short_form_max_retries_per_shot: int = 1
    long_form_max_retries_per_shot: int = 2
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

    # --- V2: AI Director (app/orchestration/planner.py) ---
    # Uses OpenAI API structured function calling to create a validated
    # ProductionPlan. OPENAI_API_KEY is separate from a ChatGPT subscription.
    # This only powers POST /projects/{id}/plan; video generation still uses
    # the configured generation provider (fal/WAN/etc.).
    llm_provider: str = "openai"
    openai_api_key: str = ""
    director_model: str = "gpt-4.1-mini"
    director_max_tokens: int = 4000

    # --- V2: Modal self-hosted Wan provider (app/services/providers/modal/) ---
    # All required (no default) once GENERATION_PROVIDER-per-model="modal"
    # is actually used for a model — see providers/modal/client.py's module
    # docstring for exactly what each of these controls and how to get it.
    modal_token_id: str = ""
    modal_token_secret: str = ""
    modal_app_name: str = "vividgen-wan"
    wan_sample_steps: int = Field(default=20, ge=1, le=50)
    wan_model: str = "wan2.2-ti2v-5b"
    wan_gpu: str = "l40s"
    wan_min_containers: int = 0
    wan_max_containers: int = 4
    wan_volume_name: str = "vividgen-wan-weights"
    wan_timeout_seconds: int = 600
    modal_webhook_secret: str = ""  # HMAC secret for POST /webhooks/modal, separate from internal_api_secret

    # --- Audio generation providers ---
    # Chatterbox is an external/self-hosted endpoint (for example the official
    # Modal example or an OpenAI-compatible Chatterbox server); its model weights
    # are intentionally not installed in the API worker container.
    tts_provider: str = "fal_chatterbox"  # fal | elevenlabs | chatterbox (self-hosted) | fal_chatterbox (managed + reference voice)
    elevenlabs_api_key: str = ""
    chatterbox_tts_base_url: str = ""
    chatterbox_tts_api_key: str = ""
    chatterbox_tts_mode: str = "openai_compatible"  # openai_compatible | modal_query
    chatterbox_tts_timeout_seconds: int = 180
    transcription_provider: str = "openai_whisper"
    openai_api_key: str = ""
    audio_generation_provider: str = "fal"
    fal_audio_music_model: str = "fal-ai/stable-audio-25/text-to-audio"
    fal_audio_ambience_model: str = "fal-ai/stable-audio-25/text-to-audio"
    audio_generation_timeout_seconds: int = 240
    audio_tts_max_concurrency: int = Field(default=4, ge=1, le=16)
    # Audio cost assumptions in USD; adjust if provider pricing or self-hosted measured unit economics change.
    audio_chatterbox_usd_per_1000_chars: float = Field(default=0.025, ge=0.0)
    audio_tts_usd_per_1000_chars: float = Field(default=0.05, ge=0.0)
    audio_bed_usd_per_generation: float = Field(default=0.20, ge=0.0)
    audio_retail_markup_multiplier: float = Field(default=3.0, ge=1.0, le=10.0)

    # --- V2: content-source workflows (URL → video, YouTube → shorts) ---
    url_fetch_timeout_seconds: int = 20
    url_fetch_max_bytes: int = 5 * 1024 * 1024

    # gap-closure (0006): stock-asset URL fetch (orchestration/asset_fetch.py)
    # downloads actual media files, not article HTML, so it needs its own,
    # much larger cap than url_fetch_max_bytes.
    stock_asset_max_bytes: int = 200 * 1024 * 1024
    respect_robots_txt: bool = True

    # --- Round 4: real external provider adapters (confirmed decisions
    # #1 and #4) — absence of these means NOT_CONFIGURED, a distinct
    # state from a runtime failure (ProviderAvailabilityStatus), never a
    # silent fallback to a different mechanism. ---
    pexels_api_key: str | None = None
    freesound_api_key: str | None = None
    stock_provider_timeout_seconds: int = 15
    url_reference_max_images: int = 3
    url_reference_max_image_bytes: int = 8 * 1024 * 1024
    # Credit-pack IDs must match the Polar products configured by Next.js.
    polar_small_credit_product_id: str = ""
    polar_medium_credit_product_id: str = ""
    polar_large_credit_product_id: str = ""
    polar_small_credit_amount: int = 10
    polar_medium_credit_amount: int = 25
    polar_large_credit_amount: int = 50
    polar_small_credit_price_usd: float = 0.0
    polar_medium_credit_price_usd: float = 0.0
    polar_large_credit_price_usd: float = 0.0
    # Per-plan defaults; individual users can receive a reviewed override via the admin entitlement endpoint.
    free_plan_monthly_video_seconds: int = 120
    free_plan_max_concurrent_generations: int = 1
    free_plan_max_project_duration_seconds: int = 120
    music_provider_timeout_seconds: int = 15

    # --- Round 4: Model Router scoring weights. Deterministic
    # application logic, not an LLM decision at execution time (per the
    # explicit requirement) — these weights are the only "judgment call"
    # in routing, and they're a fixed, inspectable config, not a prompt. ---
    router_weight_quality: float = 0.30
    router_weight_price: float = 0.20
    router_weight_health: float = 0.35
    router_weight_latency: float = 0.15
    # A candidate whose price would exceed this fraction of the
    # production's remaining budget is excluded outright (not just
    # scored down) when a production_id/remaining-budget is known.
    router_max_price_fraction_of_remaining_budget: float = 0.9

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "Settings":
        """Refuse unsafe production startup instead of silently using defaults."""
        if self.app_env != "production" and self.environment != "production":
            return self

        missing: list[str] = []
        if len(self.internal_api_secret) < 32:
            missing.append("INTERNAL_API_SECRET")
        if not self.metrics_token:
            missing.append("METRICS_TOKEN")
        if not self.backend_public_url.startswith("https://"):
            missing.append("BACKEND_PUBLIC_URL(https)")
        if not self.cors_allow_origins or any(not origin.startswith("https://") for origin in self.cors_allow_origins):
            missing.append("CORS_ALLOW_ORIGINS(https)")
        if self.generation_provider == "fal":
            if not self.fal_key:
                missing.append("FAL_KEY")
            if not self.fal_webhook_url.startswith("https://"):
                missing.append("FAL_WEBHOOK_URL(https)")
        if not self.modal_webhook_secret and self.modal_token_id:
            missing.append("MODAL_WEBHOOK_SECRET")
        if missing:
            raise ValueError("Unsafe production configuration; missing or invalid: " + ", ".join(missing))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

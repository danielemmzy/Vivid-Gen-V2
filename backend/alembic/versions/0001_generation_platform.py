"""generation platform tables (core schema)

Revision ID: 0001_generation_platform
Revises:
Create Date: 2026-08-30

Rewritten from the original 0001 to fix a schema violation: the original
had `generation.user_id` and `credit_transaction.user_id` as real foreign
keys into `user.id`. That table lives in the `auth` schema, owned and
migrated exclusively by Next.js/Prisma — a cross-schema FK couples the two
services' migration ordering together and breaks the moment Prisma
changes that table independently. Per the architecture plan's Decision 2,
user_id here is a logical reference only, enforced in application code
(via the internal-auth JWT/HMAC user_id claim), never in the database.

This migration has never been run against a real database (project is
pre-launch), so it replaces the original outright rather than patching
around a bad decision it already put in place.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_generation_platform"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "core"


def upgrade() -> None:
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')

    op.create_table(
        "ai_model",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_model_id", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("generation_type", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("commercial_use_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("supports_movie_shots", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_resolution", sa.String(16), nullable=False, server_default="1080p"),
        sa.Column("pricing_unit", sa.String(32), nullable=False),
        sa.Column("provider_price_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("price_per_unit", sa.Numeric(18, 8), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_ai_model_generation_type", "ai_model", ["generation_type"], schema=SCHEMA)
    op.bulk_insert(
        sa.table(
            "ai_model",
            sa.column("id", sa.String), sa.column("provider", sa.String), sa.column("provider_model_id", sa.String),
            sa.column("name", sa.String), sa.column("generation_type", sa.String), sa.column("enabled", sa.Boolean),
            sa.column("commercial_use_verified", sa.Boolean), sa.column("supports_movie_shots", sa.Boolean),
            sa.column("max_resolution", sa.String), sa.column("pricing_unit", sa.String),
            sa.column("provider_price_usd", sa.Numeric), sa.column("price_per_unit", sa.Numeric),
            schema=SCHEMA,
        ),
        [
            {"id": "seedream-v4", "provider": "fal", "provider_model_id": "fal-ai/bytedance/seedream/v4/text-to-image", "name": "Seedream V4", "generation_type": "text_to_image", "enabled": True, "commercial_use_verified": True, "supports_movie_shots": False, "max_resolution": "2048x2048", "pricing_unit": "image", "provider_price_usd": 0.03, "price_per_unit": 1},
            {"id": "flux-kontext-pro", "provider": "fal", "provider_model_id": "fal-ai/flux-pro/kontext", "name": "Flux Kontext Pro", "generation_type": "image_to_image", "enabled": True, "commercial_use_verified": True, "supports_movie_shots": False, "max_resolution": "2048x2048", "pricing_unit": "image", "provider_price_usd": 0.04, "price_per_unit": 1},
            {"id": "wan-2.5", "provider": "fal", "provider_model_id": "fal-ai/wan-25-preview/text-to-video", "name": "Wan 2.5", "generation_type": "text_to_video", "enabled": True, "commercial_use_verified": True, "supports_movie_shots": True, "max_resolution": "1080p", "pricing_unit": "second", "provider_price_usd": 0.05, "price_per_unit": 1},
            {"id": "kling-2.5-turbo-pro-i2v", "provider": "fal", "provider_model_id": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video", "name": "Kling 2.5 Turbo Pro I2V", "generation_type": "image_to_video", "enabled": True, "commercial_use_verified": True, "supports_movie_shots": True, "max_resolution": "1080p", "pricing_unit": "second", "provider_price_usd": 0.07, "price_per_unit": 1},
            {"id": "kling-2.5-turbo-pro", "provider": "fal", "provider_model_id": "fal-ai/kling-video/v2.5-turbo/pro/text-to-video", "name": "Kling 2.5 Turbo Pro", "generation_type": "text_to_video", "enabled": True, "commercial_use_verified": True, "supports_movie_shots": True, "max_resolution": "1080p", "pricing_unit": "second", "provider_price_usd": 0.07, "price_per_unit": 1},
            {"id": "omnihuman-1.5", "provider": "fal", "provider_model_id": "fal-ai/bytedance/omnihuman/v1.5", "name": "Omnihuman 1.5", "generation_type": "avatar", "enabled": True, "commercial_use_verified": True, "supports_movie_shots": False, "max_resolution": "1080p", "pricing_unit": "second", "provider_price_usd": 0.16, "price_per_unit": 1},
            {"id": "video-translate-dub", "provider": "fal", "provider_model_id": "fal-ai/video-translate/dub-lipsync", "name": "Video Translate + Lip-sync", "generation_type": "video_translation", "enabled": True, "commercial_use_verified": True, "supports_movie_shots": False, "max_resolution": "1080p", "pricing_unit": "minute", "provider_price_usd": 0.35, "price_per_unit": 1},
            {"id": "video-dub-audio-only", "provider": "fal", "provider_model_id": "fal-ai/video-translate/dub-audio-only", "name": "Audio-only Dub", "generation_type": "video_translation", "enabled": True, "commercial_use_verified": True, "supports_movie_shots": False, "max_resolution": "1080p", "pricing_unit": "minute", "provider_price_usd": 0.14, "price_per_unit": 1},
            {"id": "audio-replace", "provider": "fal", "provider_model_id": "fal-ai/video-audio/replace", "name": "Replace Video Audio", "generation_type": "audio_replace", "enabled": True, "commercial_use_verified": True, "supports_movie_shots": False, "max_resolution": "1080p", "pricing_unit": "minute", "provider_price_usd": 0.10, "price_per_unit": 1},
            {"id": "tts-voice-clone", "provider": "fal", "provider_model_id": "fal-ai/elevenlabs/tts/turbo-v2.5", "name": "Voice Clone TTS", "generation_type": "text_to_speech", "enabled": True, "commercial_use_verified": True, "supports_movie_shots": False, "max_resolution": "1080p", "pricing_unit": "minute", "provider_price_usd": 0.06, "price_per_unit": 1},
        ],
    )

    op.create_table(
        "project",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(191), nullable=False),  # logical ref to auth.user.id — see module docstring
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("aspect_ratio", sa.String(16), nullable=False, server_default="16:9"),
        sa.Column("resolution", sa.String(32), nullable=False, server_default="1080p"),
        sa.Column("output_s3_key", sa.String(1024)),
        sa.Column("output_duration_seconds", sa.Numeric(10, 3)),
        sa.Column("error_message", sa.Text()),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_project_user_id", "project", ["user_id"], schema=SCHEMA)
    op.create_index("ix_project_status", "project", ["status"], schema=SCHEMA)

    op.create_table(
        "character",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("project_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("reference_s3_keys", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("locked_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("voice_id", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_character_project_id", "character", ["project_id"], schema=SCHEMA)
    op.create_index("ix_character_user_id", "character", ["user_id"], schema=SCHEMA)

    op.create_table(
        "shot",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("camera_notes", sa.String(500)),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("character_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("model_id", sa.String(64)),
        sa.Column("generation_id", sa.String(32)),  # FK added after `generation` table exists, below
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_shot_project_id", "shot", ["project_id"], schema=SCHEMA)
    op.create_index("ix_shot_status", "shot", ["status"], schema=SCHEMA)

    op.create_table(
        "generation",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(191), nullable=False),  # logical ref to auth.user.id
        sa.Column("title", sa.String(200)),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("model_id", sa.String(64), sa.ForeignKey(f"{SCHEMA}.ai_model.id"), nullable=False),
        sa.Column("provider_request_id", sa.String(255), unique=True),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("prompt", sa.Text()),
        sa.Column("input_s3_key", sa.String(1024)),
        sa.Column("secondary_input_s3_key", sa.String(1024)),
        sa.Column("output_s3_key", sa.String(1024)),
        sa.Column("thumbnail_s3_key", sa.String(1024)),
        sa.Column("output_url", sa.Text()),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("duration_seconds", sa.Numeric(10, 3)),
        sa.Column("resolution", sa.String(32)),
        sa.Column("aspect_ratio", sa.String(16)),
        sa.Column("project_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.project.id", ondelete="SET NULL")),
        sa.Column("shot_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.shot.id", ondelete="SET NULL")),
        sa.Column("character_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.character.id", ondelete="SET NULL")),
        sa.Column("estimated_provider_cost_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("actual_provider_cost_usd", sa.Numeric(18, 8)),
        sa.Column("credits_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credits_charged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("moderation_verdict", sa.String(32)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_generation_user_created", "generation", ["user_id", "created_at"], schema=SCHEMA)
    op.create_index("ix_generation_status", "generation", ["status"], schema=SCHEMA)
    op.create_index("ix_generation_project_id", "generation", ["project_id"], schema=SCHEMA)
    op.create_index("ix_generation_shot_id", "generation", ["shot_id"], schema=SCHEMA)
    op.create_index("uq_generation_user_idempotency", "generation", ["user_id", "idempotency_key"], unique=True, schema=SCHEMA)

    op.create_foreign_key(
        "fk_shot_generation", "shot", "generation", ["generation_id"], ["id"],
        source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="SET NULL",
    )

    op.create_table(
        "credit_transaction",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(191), nullable=False),  # logical ref to auth.user.id
        sa.Column("generation_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.generation.id", ondelete="SET NULL")),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_before", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_credit_transaction_user_created", "credit_transaction", ["user_id", "created_at"], schema=SCHEMA)
    op.create_index("ix_credit_transaction_generation", "credit_transaction", ["generation_id"], schema=SCHEMA)

    op.create_table(
        "webhook_event",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_event_id", sa.String(255), nullable=False, unique=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("processing_error", sa.String(2000)),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_webhook_event_provider", "webhook_event", ["provider"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("webhook_event", schema=SCHEMA)
    op.drop_table("credit_transaction", schema=SCHEMA)
    op.drop_constraint("fk_shot_generation", "shot", schema=SCHEMA, type_="foreignkey")
    op.drop_table("generation", schema=SCHEMA)
    op.drop_table("shot", schema=SCHEMA)
    op.drop_table("character", schema=SCHEMA)
    op.drop_table("project", schema=SCHEMA)
    op.drop_table("ai_model", schema=SCHEMA)

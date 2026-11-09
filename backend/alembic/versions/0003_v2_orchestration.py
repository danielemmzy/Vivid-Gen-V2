"""v2 orchestration: asset + brand_kit tables

Revision ID: 0003_v2_orchestration
Revises: 0002_row_level_security
Create Date: 2026-09-06

Adds exactly two new tables for V2 Phase 8 (Asset) and Phase 11
(BrandKit, including a default_music_s3_key column for a real uploaded
background track — see models/brand_kit.py's comment on why this isn't
AI-generated music) — everything else V2 needed (Project.production_plan
storage, Generation cost-breakdown for Modal/GPU-second tracking) reuses
existing `metadata_json` JSON columns rather than adding new ones (see
V2_ARCHITECTURE_AUDIT.md's Phase 8 section for why). No changes to any
existing table in this migration.

Both new tables are user-owned (`user_id` column present, matches the
`generation`/`project`/`character` pattern from 0002), so they get the
exact same RLS treatment as those tables — a table added without RLS
would be a silent isolation gap, not just a missing feature.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_v2_orchestration"
down_revision = "0002_row_level_security"
branch_labels = None
depends_on = None

SCHEMA = "core"

_POLICY_EXPR = (
    "(current_setting('app.is_system_context', true) = 'true') "
    "OR (user_id = current_setting('app.current_user_id', true))"
)


def upgrade() -> None:
    op.create_table(
        "asset",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=False),
        sa.Column("mime_type", sa.String(120)),
        sa.Column("duration_seconds", sa.Numeric(10, 3)),
        sa.Column("scene_number", sa.Integer()),
        sa.Column("source_generation_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.generation.id", ondelete="SET NULL")),
        sa.Column("asset_metadata", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_asset_project_id", "asset", ["project_id"], schema=SCHEMA)
    op.create_index("ix_asset_user_id", "asset", ["user_id"], schema=SCHEMA)
    op.create_index("ix_asset_type", "asset", ["type"], schema=SCHEMA)

    op.create_table(
        "brand_kit",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("logo_s3_key", sa.String(1024)),
        sa.Column("watermark_s3_key", sa.String(1024)),
        sa.Column("default_music_s3_key", sa.String(1024)),
        sa.Column("intro_asset_id", sa.String(32)),
        sa.Column("outro_asset_id", sa.String(32)),
        sa.Column("primary_color", sa.String(16)),
        sa.Column("secondary_color", sa.String(16)),
        sa.Column("font_family", sa.String(120)),
        sa.Column("caption_style", sa.String(32), nullable=False, server_default="minimal"),
        sa.Column("cta_text", sa.String(200)),
        sa.Column("voice_id", sa.String(120)),
        sa.Column("extra", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_brand_kit_user_id", "brand_kit", ["user_id"], schema=SCHEMA)

    for table in ["asset", "brand_kit"]:
        op.execute(f'ALTER TABLE "{SCHEMA}"."{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{SCHEMA}"."{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY {table}_isolation ON "{SCHEMA}"."{table}" '
            f"USING ({_POLICY_EXPR}) WITH CHECK ({_POLICY_EXPR})"
        )


def downgrade() -> None:
    for table in ["asset", "brand_kit"]:
        op.execute(f'DROP POLICY IF EXISTS {table}_isolation ON "{SCHEMA}"."{table}"')
    op.drop_table("brand_kit", schema=SCHEMA)
    op.drop_table("asset", schema=SCHEMA)
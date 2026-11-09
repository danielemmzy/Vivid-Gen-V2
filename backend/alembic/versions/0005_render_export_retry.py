"""render_job + export tables; generation retry/reconciliation columns

Revision ID: 0005_render_export_retry
Revises: 0004_scene_versioning
Create Date: 2026-09-15

Closes three schema gaps found in the V2 code audit:

1. There was no persisted render observability — a Project's render step
   was only ever a 3-value status string (`assembling`/`ready`/`failed`)
   on `Project` itself, with no step list, no attempt count, no manifest
   record. `render_job` fixes that: one row per render attempt, holding
   the exact `RenderManifest` that was rendered and per-attempt status.

2. There was no `Export` concept at all — "download" meant only the
   original master's presigned URL. `export` gives Content Factory
   variants (different aspect ratio/platform) a real, listable record.

3. `Generation.retry_count`/`attempted_model_ids` are added so the new
   automatic-fallback logic (services/generation/service.py) has
   somewhere real to persist "how many times, and against which models,
   has this generation been attempted" instead of that being implicit
   and unrecoverable across process restarts.

Both new tables are user-owned, so they get the same RLS treatment as
every other user-owned table added since 0002 (asset, brand_kit).
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_render_export_retry"
down_revision = "0004_scene_versioning"
branch_labels = None
depends_on = None

SCHEMA = "core"

_POLICY_EXPR = (
    "(current_setting('app.is_system_context', true) = 'true') "
    "OR (user_id = current_setting('app.current_user_id', true))"
)


def upgrade() -> None:
    op.create_table(
        "render_job",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_step", sa.String(64)),
        sa.Column("manifest_json", sa.JSON()),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error", sa.Text()),
        sa.Column("output_asset_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.asset.id", ondelete="SET NULL")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_render_job_project_id", "render_job", ["project_id"], schema=SCHEMA)
    op.create_index("ix_render_job_user_id", "render_job", ["user_id"], schema=SCHEMA)

    op.create_table(
        "export",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("aspect_ratio", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="processing"),
        sa.Column("asset_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.asset.id", ondelete="SET NULL")),
        sa.Column("s3_key", sa.String(1024)),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_export_project_id", "export", ["project_id"], schema=SCHEMA)
    op.create_index("ix_export_user_id", "export", ["user_id"], schema=SCHEMA)

    for table in ["render_job", "export"]:
        op.execute(f'ALTER TABLE "{SCHEMA}"."{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{SCHEMA}"."{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY {table}_isolation ON "{SCHEMA}"."{table}" '
            f"USING ({_POLICY_EXPR}) WITH CHECK ({_POLICY_EXPR})"
        )

    # Generation: real retry/fallback bookkeeping (replaces the dead
    # Shot.retry_count column, which nothing ever wrote to — dropped below).
    op.add_column("generation", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"), schema=SCHEMA)
    op.add_column("generation", sa.Column("attempted_model_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")), schema=SCHEMA)

    # Shot.retry_count (added 0001) was write-only dead weight — nothing in
    # the codebase ever incremented it, and a shot's retries are really its
    # active Generation's retries (see Generation.retry_count above), not a
    # separate counter. Removing rather than leaving it silently unused.
    op.drop_column("shot", "retry_count", schema=SCHEMA)

    # BrandKit: intro/outro asset references were declared on the model
    # from 0003 but never exposed on the create/update API — no schema
    # change needed for those two (columns already exist), this is a
    # backend/API-layer fix only. No-op here, noted for completeness.


def downgrade() -> None:
    op.add_column("shot", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"), schema=SCHEMA)
    op.drop_column("generation", "attempted_model_ids", schema=SCHEMA)
    op.drop_column("generation", "retry_count", schema=SCHEMA)
    for table in ["render_job", "export"]:
        op.execute(f'DROP POLICY IF EXISTS {table}_isolation ON "{SCHEMA}"."{table}"')
    op.drop_table("export", schema=SCHEMA)
    op.drop_table("render_job", schema=SCHEMA)

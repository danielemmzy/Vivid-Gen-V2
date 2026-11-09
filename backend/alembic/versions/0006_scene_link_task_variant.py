"""shot.scene_number + ProductionTask + ContentVariant

Revision ID: 0006_scene_link_task_variant
Revises: 0005_render_export_retry
Create Date: 2026-09-17

Three more gap-closures from the follow-up pass:

1. `shot.scene_number` — a Shot had no link back to the ScenePlan.scene_number
   it was created from. This blocked real per-scene audio timing (P0.8):
   without knowing which shot corresponds to which scene, a voiceover line
   couldn't be placed at that scene's actual position in the timeline, only
   concatenated with every other line into one undifferentiated track.

2. `production_task` — a minimal, real (if not fully dependency-graph-aware)
   per-step observability table. One row per scene per project, tracking
   that scene's generation status independent of (but linked to) its Shot —
   this is intentionally NOT the full spec's arbitrary-dependency DAG
   (research -> scene -> voice -> music -> caption -> brand -> render, with
   parallel/sequential edges); it is a flat, always-parallel task list that
   makes "what step is this project on and did it succeed" queryable
   per-scene without inventing a dependency-graph engine this pass didn't
   have time to build correctly. See orchestration/production_task.py.

3. `content_variant` — splits what the previous pass collapsed into one
   `Export` row into two stages: a `ContentVariant` (an aspect-ratio/
   platform-reframed video derived from a project's Master) and one or more
   `Export` rows pointing at a variant (so the same 9:16 variant could, in
   principle, back more than one export — e.g. different codecs for
   different destinations, even though this pass only ever creates one
   Export per variant). `export.variant_id` is added; `export.aspect_ratio`
   is kept for backward compatibility with rows created before this
   migration but is no longer written by new code — see
   services/export/service.py.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_scene_link_task_variant"
down_revision = "0005_render_export_retry"
branch_labels = None
depends_on = None

SCHEMA = "core"

_POLICY_EXPR = (
    "(current_setting('app.is_system_context', true) = 'true') "
    "OR (user_id = current_setting('app.current_user_id', true))"
)


def upgrade() -> None:
    op.add_column("shot", sa.Column("scene_number", sa.Integer(), nullable=True), schema=SCHEMA)

    op.create_table(
        "production_task",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),   # scene | voice | captions | music | branding | render
        sa.Column("scene_number", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("shot_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.shot.id", ondelete="SET NULL")),
        sa.Column("render_job_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.render_job.id", ondelete="SET NULL")),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_production_task_project_id", "production_task", ["project_id"], schema=SCHEMA)
    op.create_index("ix_production_task_user_id", "production_task", ["user_id"], schema=SCHEMA)

    op.create_table(
        "content_variant",
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
    op.create_index("ix_content_variant_project_id", "content_variant", ["project_id"], schema=SCHEMA)
    op.create_index("ix_content_variant_user_id", "content_variant", ["user_id"], schema=SCHEMA)

    op.add_column("export", sa.Column("variant_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.content_variant.id", ondelete="CASCADE"), nullable=True), schema=SCHEMA)
    op.add_column("export", sa.Column("codec", sa.String(16), nullable=False, server_default="h264"), schema=SCHEMA)

    for table in ["production_task", "content_variant"]:
        op.execute(f'ALTER TABLE "{SCHEMA}"."{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{SCHEMA}"."{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY {table}_isolation ON "{SCHEMA}"."{table}" '
            f"USING ({_POLICY_EXPR}) WITH CHECK ({_POLICY_EXPR})"
        )


def downgrade() -> None:
    op.drop_column("export", "codec", schema=SCHEMA)
    op.drop_column("export", "variant_id", schema=SCHEMA)
    for table in ["production_task", "content_variant"]:
        op.execute(f'DROP POLICY IF EXISTS {table}_isolation ON "{SCHEMA}"."{table}"')
    op.drop_table("content_variant", schema=SCHEMA)
    op.drop_table("production_task", schema=SCHEMA)
    op.drop_column("shot", "scene_number", schema=SCHEMA)

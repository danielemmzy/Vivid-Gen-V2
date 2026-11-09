"""Round 4: Product domain, ProviderHealth, CaptionTrack/CaptionSegment,
Asset provenance columns, Shot.reference_shot_id for real scene-to-scene
continuity edges.

Revision ID: 0008_asset_model_audio_routers
Revises: 0007_production_dag_budget
Create Date: 2026-09-21

Ownership rule (confirmed): `product` is project-level/shared, same tier
as `asset`/`character`/`brand_kit` — no `production_id`. `provider_health`
is global routing telemetry, not owned by any project. `caption_track` is
production-level/execution (an artifact of a specific render), matching
`render_job`/`content_variant`.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_asset_model_audio_routers"
down_revision = "0007_production_dag_budget"
branch_labels = None
depends_on = None

SCHEMA = "core"

_POLICY_EXPR = (
    "(current_setting('app.is_system_context', true) = 'true') "
    "OR (user_id = current_setting('app.current_user_id', true))"
)


def _rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{SCHEMA}"."{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{SCHEMA}"."{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY {table}_isolation ON "{SCHEMA}"."{table}" '
        f"USING ({_POLICY_EXPR}) WITH CHECK ({_POLICY_EXPR})"
    )


def upgrade() -> None:
    # --- Product: first-class, project-level/shared (confirmed decision
    # #2 — NOT a reuse of Character) ---
    op.create_table(
        "product",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("features", sa.JSON()),
        sa.Column("variants", sa.JSON()),
        sa.Column("visual_attributes", sa.JSON()),
        sa.Column("logo_asset_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.asset.id", ondelete="SET NULL")),
        sa.Column("reference_asset_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_product_project_id", "product", ["project_id"], schema=SCHEMA)
    op.create_index("ix_product_user_id", "product", ["user_id"], schema=SCHEMA)
    _rls("product")

    # --- ProviderHealth: persistent routing telemetry, updated
    # incrementally from resolved GenerationAttempt/stock/music calls
    # (confirmed decision #3). Not project-owned — no user_id/RLS; this
    # is system-wide operational data, same trust tier as the `ai_model`
    # catalog. capability distinguishes e.g. fal's text_to_video health
    # from fal's text_to_image health under the same "provider". ---
    op.create_table(
        "provider_health",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model_id", sa.String(64)),  # null for provider-level health (e.g. "pexels" has no model_id)
        sa.Column("capability", sa.String(32)),  # "text_to_video" | "stock_image" | "music" | ...
        sa.Column("status", sa.String(32), nullable=False, server_default="available"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timeout_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_latency_ms", sa.Numeric(10, 2)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_failure_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "model_id", "capability", name="uq_provider_health_key"),
        schema=SCHEMA,
    )
    op.create_index("ix_provider_health_provider", "provider_health", ["provider"], schema=SCHEMA)
    # No RLS: provider_health is not user-owned data.

    # --- CaptionTrack + CaptionSegment: first-class, queryable, not just
    # an .srt file wrapped in an Asset row. Production-level/execution
    # (an artifact of one production's render). ---
    op.create_table(
        "caption_track",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("production_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.production.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("language", sa.String(16), nullable=False, server_default="en"),
        sa.Column("style", sa.String(32), nullable=False, server_default="minimal"),
        sa.Column("font_family", sa.String(64)),
        sa.Column("primary_color", sa.String(16)),
        sa.Column("secondary_color", sa.String(16)),
        sa.Column("source_asset_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.asset.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_caption_track_production_id", "caption_track", ["production_id"], schema=SCHEMA)
    op.create_index("ix_caption_track_user_id", "caption_track", ["user_id"], schema=SCHEMA)
    _rls("caption_track")

    op.create_table(
        "caption_segment",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("caption_track_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.caption_track.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Numeric(10, 3), nullable=False),
        sa.Column("end_seconds", sa.Numeric(10, 3), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("speaker", sa.String(64)),
        schema=SCHEMA,
    )
    op.create_index("ix_caption_segment_caption_track_id", "caption_segment", ["caption_track_id"], schema=SCHEMA)
    _rls("caption_segment")

    # --- Asset: real provenance/licensing columns (confirmed requirement
    # — not buried-only in asset_metadata JSON, since the Asset Router
    # needs to filter/query on these, e.g. "only CC0 stock assets"). ---
    op.add_column("asset", sa.Column("license", sa.String(64)), schema=SCHEMA)
    op.add_column("asset", sa.Column("attribution", sa.Text()), schema=SCHEMA)
    op.add_column("asset", sa.Column("source_provider", sa.String(32)), schema=SCHEMA)  # "pexels" | "freesound" | "brand_kit" | "generation" | "upload" | ...
    op.add_column("asset", sa.Column("source_external_id", sa.String(191)), schema=SCHEMA)
    op.add_column("asset", sa.Column("width", sa.Integer()), schema=SCHEMA)
    op.add_column("asset", sa.Column("height", sa.Integer()), schema=SCHEMA)

    # --- Shot.reference_shot_id: real scene-to-scene continuity
    # (confirmed decision #5) — set only when the ProductionPlan
    # explicitly declares scene B's `reference_scene_number` pointing at
    # an earlier scene, never invented by the executor. self-referential
    # FK, SET NULL on delete so removing a shot doesn't cascade-delete
    # everything that once referenced it. ---
    op.add_column("shot", sa.Column("reference_shot_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.shot.id", ondelete="SET NULL")), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("shot", "reference_shot_id", schema=SCHEMA)

    for col in ["height", "width", "source_external_id", "source_provider", "attribution", "license"]:
        op.drop_column("asset", col, schema=SCHEMA)

    op.execute(f'DROP POLICY IF EXISTS caption_segment_isolation ON "{SCHEMA}"."caption_segment"')
    op.drop_table("caption_segment", schema=SCHEMA)
    op.execute(f'DROP POLICY IF EXISTS caption_track_isolation ON "{SCHEMA}"."caption_track"')
    op.drop_table("caption_track", schema=SCHEMA)

    op.drop_table("provider_health", schema=SCHEMA)

    op.execute(f'DROP POLICY IF EXISTS product_isolation ON "{SCHEMA}"."product"')
    op.drop_table("product", schema=SCHEMA)

"""Persist continuity frame cache and short/long production budget policies."""
from alembic import op
import sqlalchemy as sa

revision = "0011_multishot_resume_continuity"
down_revision = "0010_model_caps_cost_source"
branch_labels = None
depends_on = None
SCHEMA = "core"


def upgrade() -> None:
    op.add_column("shot", sa.Column("reference_frame_s3_key", sa.String(length=1024), nullable=True), schema=SCHEMA)
    op.add_column("shot", sa.Column("reference_frame_generation_id", sa.String(length=32), nullable=True), schema=SCHEMA)
    op.add_column("shot", sa.Column("continuity_mode", sa.String(length=32), nullable=False, server_default="none"), schema=SCHEMA)
    op.add_column("shot", sa.Column("timeline_duration_seconds", sa.Numeric(8, 3), nullable=True), schema=SCHEMA)
    op.add_column("shot", sa.Column("product_id", sa.String(length=32), nullable=True), schema=SCHEMA)
    op.create_foreign_key(
        "fk_shot_product_id_product", "shot", "product", ["product_id"], ["id"],
        source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="SET NULL",
    )
    op.add_column("production_budget", sa.Column("budget_profile", sa.String(length=24), nullable=False, server_default="short_form"), schema=SCHEMA)
    op.add_column("production_budget", sa.Column("max_shots", sa.Integer(), nullable=False, server_default="20"), schema=SCHEMA)
    op.add_column("production_budget", sa.Column("max_retries_per_shot", sa.Integer(), nullable=False, server_default="1"), schema=SCHEMA)
    # A user-uploaded clip is a zero-inference pass-through, but Generation.model_id
    # is a required FK. Keep an internal, disabled catalog row for that provenance
    # rather than misattributing the asset to a paid AI model.
    # Execute this literal SQL directly. SQLAlchemy's ``text()`` parser treats
    # the JSON fragment ``$1`` as a bind parameter on PostgreSQL, which makes a
    # fresh migration chain fail even though the statement has no parameters.
    op.get_bind().exec_driver_sql(f"""
        INSERT INTO "{SCHEMA}".ai_model
            (id, provider, provider_model_id, name, generation_type, enabled, commercial_use_verified,
             supports_movie_shots, max_resolution, pricing_unit, provider_price_usd, price_per_unit,
             retail_multiplier, capabilities, cost_strategy, cost_estimate_basis, created_at, updated_at)
        VALUES
            ('user-asset-passthrough', 'internal', 'vividgen/user-asset-passthrough',
             'Uploaded asset (pass-through)', 'movie_shot', false, false, false, '720p', 'flat',
             0, 0, 2.5, '{{"input_type":"asset_passthrough","movie_shots":false}}'::json,
             'catalog_unit_price', 'zero-cost uploaded asset pass-through', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (id) DO NOTHING
    """)

def downgrade() -> None:
    # Keep the internal catalog row if historical pass-through generations still reference it.
    op.execute(sa.text(f"""DELETE FROM "{SCHEMA}".ai_model WHERE id = 'user-asset-passthrough' AND NOT EXISTS (SELECT 1 FROM "{SCHEMA}".generation WHERE model_id = 'user-asset-passthrough')"""))
    op.drop_constraint("fk_shot_product_id_product", "shot", schema=SCHEMA, type_="foreignkey")
    op.drop_column("shot", "product_id", schema=SCHEMA)
    op.drop_column("production_budget", "max_retries_per_shot", schema=SCHEMA)
    op.drop_column("production_budget", "max_shots", schema=SCHEMA)
    op.drop_column("production_budget", "budget_profile", schema=SCHEMA)
    op.drop_column("shot", "timeline_duration_seconds", schema=SCHEMA)
    op.drop_column("shot", "continuity_mode", schema=SCHEMA)
    op.drop_column("shot", "reference_frame_generation_id", schema=SCHEMA)
    op.drop_column("shot", "reference_frame_s3_key", schema=SCHEMA)

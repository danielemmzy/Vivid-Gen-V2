"""Refresh the model catalog and make retail pricing model-specific.

Keeps old model rows for historical generations but disables obsolete defaults.
Adds FLUX.2 image models and the official Wan2.2 TI2V-5B Modal models.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_model_catalog_pricing"
down_revision = "0008_asset_model_audio_routers"
branch_labels = None
depends_on = None
SCHEMA = "core"


def upgrade() -> None:
    op.add_column("ai_model", sa.Column("retail_multiplier", sa.Numeric(8, 4), nullable=False, server_default="2.5"), schema=SCHEMA)
    op.execute(sa.text(f'UPDATE "{SCHEMA}"."ai_model" SET retail_multiplier = 2.5'))
    op.execute(sa.text(f"UPDATE \"{SCHEMA}\".\"ai_model\" SET enabled = false WHERE id IN ('seedream-v4', 'wan-2.5')"))

    table = sa.table(
        "ai_model",
        sa.column("id", sa.String), sa.column("provider", sa.String), sa.column("provider_model_id", sa.String),
        sa.column("name", sa.String), sa.column("generation_type", sa.String), sa.column("enabled", sa.Boolean),
        sa.column("commercial_use_verified", sa.Boolean), sa.column("supports_movie_shots", sa.Boolean),
        sa.column("max_resolution", sa.String), sa.column("pricing_unit", sa.String),
        sa.column("provider_price_usd", sa.Numeric), sa.column("price_per_unit", sa.Numeric),
        sa.column("retail_multiplier", sa.Numeric), schema=SCHEMA,
    )
    rows = [
        ("flux-2-turbo", "fal", "fal-ai/flux-2/turbo", "FLUX.2 Turbo", "text_to_image", 0.008, 2.5),
        ("flux-2", "fal", "fal-ai/flux-2", "FLUX.2", "text_to_image", 0.012, 2.5),
        ("flux-2-turbo-edit", "fal", "fal-ai/flux-2/turbo/edit", "FLUX.2 Turbo Edit", "image_to_image", 0.016, 2.5),
        ("wan-2.2-ti2v-5b", "modal", "wan2.2-ti2v-5b", "Wan 2.2 TI2V-5B (Modal)", "text_to_video", 0.01, 2.0),
        ("wan-2.2-ti2v-5b-i2v", "modal", "wan2.2-ti2v-5b-i2v", "Wan 2.2 TI2V-5B I2V (Modal)", "image_to_video", 0.01, 2.0),
    ]
    for model_id, provider, provider_model_id, name, generation_type, price, multiplier in rows:
        op.bulk_insert(table, [{
            "id": model_id, "provider": provider, "provider_model_id": provider_model_id, "name": name,
            "generation_type": generation_type, "enabled": True, "commercial_use_verified": True,
            "supports_movie_shots": generation_type in ("text_to_video", "image_to_video"),
            "max_resolution": "720p" if provider == "modal" else "2048x2048",
            "pricing_unit": "second" if provider == "modal" else "image",
            "provider_price_usd": price, "price_per_unit": 1, "retail_multiplier": multiplier,
        }])


def downgrade() -> None:
    op.execute(sa.text(f"DELETE FROM \"{SCHEMA}\".\"ai_model\" WHERE id IN ('flux-2-turbo', 'flux-2', 'flux-2-turbo-edit', 'wan-2.2-ti2v-5b', 'wan-2.2-ti2v-5b-i2v')"))
    op.drop_column("ai_model", "retail_multiplier", schema=SCHEMA)

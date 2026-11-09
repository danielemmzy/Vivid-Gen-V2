"""shot: add generation_history for scene versioning (B08)

Revision ID: 0004_scene_versioning
Revises: 0003_v2_orchestration
Create Date: 2026-09-13

Unlike 0003 (which created brand-new, never-deployed tables and so could
be edited in place this session), `shot` already exists in the real
database from migration 0001 — this is a genuine ALTER on a live table,
backfilled to an empty list so existing rows don't get NULL.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_scene_versioning"
down_revision = "0003_v2_orchestration"
branch_labels = None
depends_on = None

SCHEMA = "core"


def upgrade() -> None:
    op.add_column(
        "shot",
        sa.Column("generation_history", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("shot", "generation_history", schema=SCHEMA)
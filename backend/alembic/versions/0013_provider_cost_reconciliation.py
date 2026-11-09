"""Add auditable provider usage/invoice evidence for cost reconciliation."""
from alembic import op
import sqlalchemy as sa

revision = "0013_provider_cost_reconciliation"
down_revision = "0012_launch_hardening"
branch_labels = None
depends_on = None
SCHEMA = "core"


def upgrade() -> None:
    # This revision is 33 characters long, while Alembic's default version
    # table is VARCHAR(32). Widen it before Alembic records this revision;
    # otherwise a fresh database fails after all application DDL succeeds.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        schema=SCHEMA,
    )
    op.create_table(
        "provider_cost_record",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_reference", sa.String(length=255), nullable=False),
        sa.Column("generation_id", sa.String(length=32), nullable=True),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("provider_model_id", sa.String(length=255), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("invoice_reference", sa.String(length=255), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("reported_cost_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("variance_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("reconciliation_status", sa.String(length=24), nullable=False, server_default="unmatched"),
        sa.Column("raw_record", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["generation_id"], ["core.generation.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("provider", "external_reference", name="uq_provider_cost_external_reference"),
        schema=SCHEMA,
    )
    op.create_index("ix_provider_cost_generation", "provider_cost_record", ["generation_id"], schema=SCHEMA)
    op.create_index("ix_provider_cost_reconciliation_status", "provider_cost_record", ["reconciliation_status"], schema=SCHEMA)
    op.execute('ALTER TABLE "core"."provider_cost_record" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "core"."provider_cost_record" FORCE ROW LEVEL SECURITY')
    op.execute("""CREATE POLICY provider_cost_record_isolation ON core.provider_cost_record
        USING (current_setting('app.is_system_context', true) = 'true')
        WITH CHECK (current_setting('app.is_system_context', true) = 'true')""")


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS provider_cost_record_isolation ON "core"."provider_cost_record"')
    op.execute('ALTER TABLE "core"."provider_cost_record" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "core"."provider_cost_record" DISABLE ROW LEVEL SECURITY')
    op.drop_index("ix_provider_cost_reconciliation_status", table_name="provider_cost_record", schema=SCHEMA)
    op.drop_index("ix_provider_cost_generation", table_name="provider_cost_record", schema=SCHEMA)
    op.drop_table("provider_cost_record", schema=SCHEMA)

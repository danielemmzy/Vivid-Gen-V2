"""Phase 8 launch hardening: static visual references, idempotent purchases and plan entitlements."""
from alembic import op
import sqlalchemy as sa

revision = "0012_launch_hardening"
down_revision = "0011_multishot_resume_continuity"
branch_labels = None
depends_on = None
SCHEMA = "core"


def upgrade() -> None:
    op.add_column("shot", sa.Column("reference_image_s3_key", sa.String(length=1024), nullable=True), schema=SCHEMA)
    op.add_column("credit_transaction", sa.Column("external_reference", sa.String(length=191), nullable=True), schema=SCHEMA)
    op.create_index("uq_credit_transaction_external_reference", "credit_transaction", ["external_reference"], unique=True, schema=SCHEMA, postgresql_where=sa.text("external_reference IS NOT NULL"))
    op.create_table(
        "user_entitlement",
        sa.Column("user_id", sa.String(length=191), primary_key=True),
        sa.Column("plan_key", sa.String(length=32), nullable=False, server_default="free"),
        sa.Column("overrides", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.execute('ALTER TABLE "core"."user_entitlement" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "core"."user_entitlement" FORCE ROW LEVEL SECURITY')
    op.execute("""CREATE POLICY user_entitlement_isolation ON core.user_entitlement USING (current_setting('app.is_system_context', true) = 'true' OR user_id = current_setting('app.current_user_id', true)) WITH CHECK (current_setting('app.is_system_context', true) = 'true' OR user_id = current_setting('app.current_user_id', true))""")


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS user_entitlement_isolation ON "core"."user_entitlement"')
    op.execute('ALTER TABLE "core"."user_entitlement" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "core"."user_entitlement" DISABLE ROW LEVEL SECURITY')
    op.drop_table("user_entitlement", schema=SCHEMA)
    op.drop_index("uq_credit_transaction_external_reference", table_name="credit_transaction", schema=SCHEMA)
    op.drop_column("credit_transaction", "external_reference", schema=SCHEMA)
    op.drop_column("shot", "reference_image_s3_key", schema=SCHEMA)

"""Production domain: Production, ProductionPlan, ProductionBudget(+ledger),
GenerationAttempt, ProductionTaskDependency, and production_id linkage on
execution-owned tables.

Revision ID: 0007_production_dag_budget
Revises: 0006_scene_link_task_variant
Create Date: 2026-09-18

This is the structural change requested explicitly: a Production run was
previously implicit (Project.status + a JSON blob in
Project.metadata_json); ProductionTask (0006) was a flat, always-parallel
list with no real dependency graph; there was no budget ledger and no
per-attempt generation history distinct from Generation's own
retry_count/attempted_model_ids counters.

Ownership rule applied throughout (as specified): Asset/Character/
BrandKit remain project-level/shared — no production_id is added to them.
Production/ProductionPlan/ProductionBudget/ProductionTask/
GenerationAttempt/RenderJob/ContentVariant/Export are production-level —
each gets a production_id. project_id is KEPT on every one of these
(not removed) so existing project-scoped queries/RLS continue to work
unchanged; production_id is additive, not a replacement.

A Project can now have multiple Productions (one per approved plan / one
per "generate" run) — `project.current_production_id` points at the most
recent one for convenience, but is not the source of truth; querying
`production` by `project_id` is.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_production_dag_budget"
down_revision = "0006_scene_link_task_variant"
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
    # ---------------------------------------------------------------
    # Production — the first-class "this particular production run of
    # this project" object. See models/production.py.
    # ---------------------------------------------------------------
    op.create_table(
        "production",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("planning_status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("execution_status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("production_type", sa.String(32), nullable=False, server_default="video"),
        sa.Column("plan_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_production_project_id", "production", ["project_id"], schema=SCHEMA)
    op.create_index("ix_production_user_id", "production", ["user_id"], schema=SCHEMA)
    _rls("production")

    # project.current_production_id — convenience pointer, not source of truth.
    op.add_column("project", sa.Column("current_production_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.production.id", ondelete="SET NULL")), schema=SCHEMA)

    # ---------------------------------------------------------------
    # ProductionPlan — moves the canonical plan out of
    # Project.metadata_json into its own versioned, queryable table.
    # Project.metadata_json is left in place for one more release as a
    # read-compat fallback (see orchestration/executor.py::load_plan) but
    # is no longer written to by new code.
    # ---------------------------------------------------------------
    op.create_table(
        "production_plan",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("production_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.production.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("director_input", sa.JSON()),
        sa.Column("plan_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.create_index("ix_production_plan_production_id", "production_plan", ["production_id"], schema=SCHEMA)
    op.create_index("ix_production_plan_project_id", "production_plan", ["project_id"], schema=SCHEMA)
    op.create_index("ix_production_plan_user_id", "production_plan", ["user_id"], schema=SCHEMA)
    _rls("production_plan")

    # ---------------------------------------------------------------
    # ProductionBudget + ledger — estimate -> reserve -> execute ->
    # reconcile -> refund, as a real traceable lifecycle instead of a
    # single mutated balance field.
    # ---------------------------------------------------------------
    op.create_table(
        "production_budget",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("production_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.production.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="credits"),
        sa.Column("estimated_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refunded_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="estimated"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_production_budget_production_id", "production_budget", ["production_id"], schema=SCHEMA)
    op.create_index("ix_production_budget_user_id", "production_budget", ["user_id"], schema=SCHEMA)
    _rls("production_budget")

    op.create_table(
        "production_budget_ledger",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("production_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.production.id", ondelete="CASCADE"), nullable=False),
        sa.Column("budget_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.production_budget.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reference_type", sa.String(32)),  # "generation" | "production_task" | ...
        sa.Column("reference_id", sa.String(32)),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_production_budget_ledger_production_id", "production_budget_ledger", ["production_id"], schema=SCHEMA)
    op.create_index("ix_production_budget_ledger_budget_id", "production_budget_ledger", ["budget_id"], schema=SCHEMA)
    op.create_index("ix_production_budget_ledger_user_id", "production_budget_ledger", ["user_id"], schema=SCHEMA)
    _rls("production_budget_ledger")

    # ---------------------------------------------------------------
    # GenerationAttempt — additive per-attempt audit history alongside
    # Generation.retry_count/attempted_model_ids (which remain the
    # authoritative retry-loop counters; this is the queryable record of
    # each individual try).
    # ---------------------------------------------------------------
    op.create_table(
        "generation_attempt",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("generation_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.generation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("production_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.production.id", ondelete="CASCADE")),
        sa.Column("production_task_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.production_task.id", ondelete="SET NULL")),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(32)),
        sa.Column("model_id", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False, server_default="submitted"),
        sa.Column("estimated_cost_usd", sa.Numeric(18, 8)),
        sa.Column("actual_cost_usd", sa.Numeric(18, 8)),
        sa.Column("failure_type", sa.String(32)),  # ProviderErrorClass, if failed
        sa.Column("error", sa.Text()),
        sa.Column("request_metadata", sa.JSON()),
        sa.Column("response_metadata", sa.JSON()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.create_index("ix_generation_attempt_generation_id", "generation_attempt", ["generation_id"], schema=SCHEMA)
    op.create_index("ix_generation_attempt_production_id", "generation_attempt", ["production_id"], schema=SCHEMA)
    op.create_index("ix_generation_attempt_user_id", "generation_attempt", ["user_id"], schema=SCHEMA)
    _rls("generation_attempt")

    # ---------------------------------------------------------------
    # ProductionTaskDependency — a real relational directed graph, not a
    # JSON depends_on field. (upstream_task_id, downstream_task_id) is
    # unique so the same edge can't be recorded twice.
    # ---------------------------------------------------------------
    op.create_table(
        "production_task_dependency",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("production_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.production.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(191), nullable=False),
        sa.Column("upstream_task_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.production_task.id", ondelete="CASCADE"), nullable=False),
        sa.Column("downstream_task_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.production_task.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dependency_type", sa.String(32), nullable=False, server_default="requires"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("upstream_task_id", "downstream_task_id", name="uq_production_task_dependency_edge"),
        schema=SCHEMA,
    )
    op.create_index("ix_production_task_dependency_production_id", "production_task_dependency", ["production_id"], schema=SCHEMA)
    op.create_index("ix_production_task_dependency_upstream", "production_task_dependency", ["upstream_task_id"], schema=SCHEMA)
    op.create_index("ix_production_task_dependency_downstream", "production_task_dependency", ["downstream_task_id"], schema=SCHEMA)
    _rls("production_task_dependency")

    # ---------------------------------------------------------------
    # production_task (0006): add production_id, output_json (each
    # task's produced artifact references — e.g. the VOICE task stores
    # its synthesized segment asset refs here, which the RENDER task
    # then reads rather than re-deriving), and a label for non-scene
    # tasks. status column already exists (string) — BLOCKED/READY are
    # new allowed values, no schema change needed for those.
    # ---------------------------------------------------------------
    op.add_column("production_task", sa.Column("production_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.production.id", ondelete="CASCADE")), schema=SCHEMA)
    op.add_column("production_task", sa.Column("output_json", sa.JSON()), schema=SCHEMA)
    op.create_index("ix_production_task_production_id", "production_task", ["production_id"], schema=SCHEMA)

    # ---------------------------------------------------------------
    # production_id on execution-owned tables (ownership rule: Asset/
    # Character/BrandKit are explicitly NOT touched — they stay
    # project-level/shared).
    # ---------------------------------------------------------------
    for table in ["shot", "generation", "render_job", "content_variant", "export"]:
        op.add_column(table, sa.Column("production_id", sa.String(32), sa.ForeignKey(f"{SCHEMA}.production.id", ondelete="SET NULL")), schema=SCHEMA)
        op.create_index(f"ix_{table}_production_id", table, ["production_id"], schema=SCHEMA)


def downgrade() -> None:
    for table in ["shot", "generation", "render_job", "content_variant", "export"]:
        op.drop_index(f"ix_{table}_production_id", table_name=table, schema=SCHEMA)
        op.drop_column(table, "production_id", schema=SCHEMA)

    op.drop_index("ix_production_task_production_id", table_name="production_task", schema=SCHEMA)
    op.drop_column("production_task", "output_json", schema=SCHEMA)
    op.drop_column("production_task", "production_id", schema=SCHEMA)

    for table in ["production_task_dependency", "generation_attempt", "production_budget_ledger", "production_budget", "production_plan"]:
        op.execute(f'DROP POLICY IF EXISTS {table}_isolation ON "{SCHEMA}"."{table}"')
        op.drop_table(table, schema=SCHEMA)

    op.drop_column("project", "current_production_id", schema=SCHEMA)

    op.execute(f'DROP POLICY IF EXISTS production_isolation ON "{SCHEMA}"."production"')
    op.drop_table("production", schema=SCHEMA)

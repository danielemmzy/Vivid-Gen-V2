"""row level security on user-owned core tables

Revision ID: 0002_row_level_security
Revises: 0001_generation_platform
Create Date: 2026-09-01

Why this exists: every query in the repository layer already filters by
`user_id`, and that's necessary but not sufficient — it means isolation
depends on every current AND future query remembering to add that filter.
One missed `WHERE` in a new endpoint, an admin debugging script, or a
future contributor who doesn't know the convention, and the database
happily hands back every user's data to whoever asked.

RLS moves that guarantee into Postgres itself: even a raw `SELECT * FROM
generation` run by the application's own DB role returns only the calling
user's rows, because the policy is evaluated by the database, not trusted
to be evaluated by the application. Two ways in:

  * app.current_user_id  — set once per request by core/database.py's
    get_db(), scoped to that request's transaction only.
  * app.is_system_context — set by system_session()/get_db_as_system()
    for jobs, the scheduler, webhooks, and admin tooling that legitimately
    need cross-user access. This is a deliberate, narrow bypass — every
    place that sets it is a place a human decided needs it, not a default.

IMPORTANT — a common RLS footgun this migration avoids: policies are
bypassed by the table owner by default. If your application connects as
the same role that owns these tables (common in a simple setup), RLS
would silently do nothing. `FORCE ROW LEVEL SECURITY` closes that gap —
see the FORCE statements below. If you later split into a dedicated
low-privilege app role (recommended for production — see the migration's
final comment block), FORCE becomes belt-and-suspenders rather than
load-bearing, which is the right end state.
"""
from alembic import op

revision = "0002_row_level_security"
down_revision = "0001_generation_platform"
branch_labels = None
depends_on = None

SCHEMA = "core"
USER_OWNED_TABLES = ["generation", "credit_transaction", "project", "character"]

_POLICY_EXPR = (
    "(current_setting('app.is_system_context', true) = 'true') "
    "OR (user_id = current_setting('app.current_user_id', true))"
)


def upgrade() -> None:
    for table in USER_OWNED_TABLES:
        op.execute(f'ALTER TABLE "{SCHEMA}"."{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{SCHEMA}"."{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY {table}_isolation ON "{SCHEMA}"."{table}" '
            f"USING ({_POLICY_EXPR}) WITH CHECK ({_POLICY_EXPR})"
        )

    # `shot` has no user_id column of its own (it's scoped through its
    # parent project) — give it a policy that joins through project instead.
    op.execute(f'ALTER TABLE "{SCHEMA}"."shot" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{SCHEMA}"."shot" FORCE ROW LEVEL SECURITY')
    op.execute(f'DROP POLICY IF EXISTS shot_isolation ON "{SCHEMA}"."shot"')
    op.execute(
        f'CREATE POLICY shot_isolation ON "{SCHEMA}"."shot" USING ('
        f"current_setting('app.is_system_context', true) = 'true' "
        f"OR project_id IN (SELECT id FROM \"{SCHEMA}\".project WHERE user_id = current_setting('app.current_user_id', true))"
        f") WITH CHECK ("
        f"current_setting('app.is_system_context', true) = 'true' "
        f"OR project_id IN (SELECT id FROM \"{SCHEMA}\".project WHERE user_id = current_setting('app.current_user_id', true))"
        f")"
    )

    # ai_model (shared catalog, no owner) and webhook_event (system-only,
    # never read with a user context) deliberately get no RLS policy —
    # RLS is for owned rows, not global config or internal audit tables.


def downgrade() -> None:
    for table in [*USER_OWNED_TABLES, "shot"]:
        op.execute(f'DROP POLICY IF EXISTS {table}_isolation ON "{SCHEMA}"."{table}"')
        op.execute(f'ALTER TABLE "{SCHEMA}"."{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{SCHEMA}"."{table}" DISABLE ROW LEVEL SECURITY')

# Production hardening note (not executed by this migration — depends on
# infra you provision): create a dedicated, non-owning `vividgen_app` role
# with only DML grants (SELECT/INSERT/UPDATE/DELETE, no DDL, not a table
# owner) and point DATABASE_URL at it instead of the migration-owning
# role. That makes FORCE ROW LEVEL SECURITY belt-and-suspenders instead of
# the only thing standing between the app role and an RLS bypass:
#
#   CREATE ROLE vividgen_app LOGIN PASSWORD '...';
#   GRANT USAGE ON SCHEMA core TO vividgen_app;
#   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core TO vividgen_app;
#   ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO vividgen_app;

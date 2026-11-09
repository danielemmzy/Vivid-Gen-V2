"""Widen core VARCHAR(32) columns while preserving dependent constraints and RLS policies.

Revision ID: 0014_widen_varchar32_columns
Revises: 0013_provider_cost_reconciliation
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_widen_varchar32_columns"
down_revision = "0013_provider_cost_reconciliation"
branch_labels = None
depends_on = None

SCHEMA = "core"
NEW_LENGTH = 128
OLD_LENGTH = 32


def _quote(identifier: str) -> str:
    return op.get_bind().dialect.identifier_preparer.quote(identifier)


def _columns_to_widen():
    return op.get_bind().execute(sa.text("""
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = :schema
          AND data_type = 'character varying'
          AND character_maximum_length = :old_length
        ORDER BY table_name, ordinal_position
    """), {"schema": SCHEMA, "old_length": OLD_LENGTH}).mappings().all()


def _foreign_keys():
    # All core-schema FKs are captured and restored with their exact definitions.
    return op.get_bind().execute(sa.text("""
        SELECT tc.table_schema, tc.table_name, tc.constraint_name,
               pg_get_constraintdef(c.oid) AS definition
        FROM information_schema.table_constraints tc
        JOIN pg_constraint c
          ON c.conname = tc.constraint_name
         AND c.conrelid = (quote_ident(tc.table_schema) || '.' || quote_ident(tc.table_name))::regclass
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = :schema
        ORDER BY tc.table_name, tc.constraint_name
    """), {"schema": SCHEMA}).mappings().all()


def _dependent_policies(columns):
    """Find policies with catalog-tracked dependencies on any column being widened."""
    if not columns:
        return []
    return op.get_bind().execute(sa.text("""
        SELECT DISTINCT p.schemaname, p.tablename, p.policyname,
               p.permissive, p.roles, p.cmd, p.qual, p.with_check
        FROM pg_policies p
        JOIN pg_class policy_table
          ON policy_table.oid = (quote_ident(p.schemaname) || '.' || quote_ident(p.tablename))::regclass
        JOIN pg_policy pol ON pol.polrelid = policy_table.oid
        JOIN pg_depend dep
          ON dep.classid = 'pg_policy'::regclass
         AND dep.objid = pol.oid
         AND dep.refclassid = 'pg_class'::regclass
        JOIN pg_attribute att
          ON att.attrelid = dep.refobjid
         AND att.attnum = dep.refobjsubid
         AND att.attnum > 0
        JOIN pg_class target_table ON target_table.oid = att.attrelid
        JOIN information_schema.columns col
          ON col.table_schema = target_table.relnamespace::regnamespace::text
         AND col.table_name = target_table.relname
         AND col.column_name = att.attname
        WHERE col.table_schema = :schema
          AND col.data_type = 'character varying'
          AND col.character_maximum_length = :old_length
        ORDER BY p.schemaname, p.tablename, p.policyname
    """), {"schema": SCHEMA, "old_length": OLD_LENGTH}).mappings().all()


def _policy_sql(policy) -> str:
    quote = _quote
    table = f'{quote(policy["schemaname"])}.{quote(policy["tablename"])}'
    mode = "PERMISSIVE" if policy["permissive"] == "PERMISSIVE" else "RESTRICTIVE"
    command = policy["cmd"]
    roles = policy["roles"] or ["public"]
    role_sql = ", ".join("PUBLIC" if role.lower() == "public" else quote(role) for role in roles)
    sql = (
        f'CREATE POLICY {quote(policy["policyname"])} ON {table} '
        f'AS {mode} FOR {command} TO {role_sql}'
    )
    if policy["qual"] is not None:
        sql += f' USING ({policy["qual"]})'
    if policy["with_check"] is not None:
        sql += f' WITH CHECK ({policy["with_check"]})'
    return sql


def upgrade() -> None:
    bind = op.get_bind()
    columns = _columns_to_widen()
    if not columns:
        return

    # Only policies that actually depend on a column being altered are removed.
    policies = _dependent_policies(columns)
    fks = _foreign_keys()

    for policy in policies:
        table = f'{_quote(policy["schemaname"])}.{_quote(policy["tablename"])}'
        op.execute(sa.text(
            f' DROP POLICY {_quote(policy["policyname"])} ON {table}'
        ))

    for fk in fks:
        table = f'{_quote(fk["table_schema"])}.{_quote(fk["table_name"])}'
        op.execute(sa.text(
            f'ALTER TABLE {table} DROP CONSTRAINT {_quote(fk["constraint_name"])}'
        ))

    for column in columns:
        table = f'{_quote(SCHEMA)}.{_quote(column["table_name"])}'
        col = _quote(column["column_name"])
        op.execute(sa.text(
            f'ALTER TABLE {table} ALTER COLUMN {col} TYPE VARCHAR({NEW_LENGTH})'
        ))

    for fk in fks:
        table = f'{_quote(fk["table_schema"])}.{_quote(fk["table_name"])}'
        op.execute(sa.text(
            f'ALTER TABLE {table} ADD CONSTRAINT {_quote(fk["constraint_name"])} {fk["definition"]}'
        ))

    for policy in policies:
        op.execute(sa.text(_policy_sql(policy)))


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade intentionally disabled: widening columns is backward-compatible, "
        "and narrowing them could fail or truncate future data."
    )

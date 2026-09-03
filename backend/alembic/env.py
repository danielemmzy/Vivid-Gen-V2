from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from app.core.config import settings
from app.models import Base  # noqa: F401 - imports every model module so metadata is fully populated

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)
if config.config_file_name:
    fileConfig(config.config_file_name)

# Autogenerate now actually works against our schema instead of producing
# an empty migration — this was previously wired to None, which is a
# silent footgun (alembic revision --autogenerate would just do nothing).
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(
        url=settings.database_url, literal_binds=True, dialect_opts={"paramstyle": "named"},
        target_metadata=target_metadata, version_table_schema=settings.database_schema,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        # Ensure the `core` schema exists before Alembic tries to create
        # tables in it — a fresh database won't have it yet.
        from sqlalchemy import text
        await connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{settings.database_schema}"'))
        await connection.run_sync(
            lambda c: context.configure(
                connection=c, target_metadata=target_metadata,
                version_table_schema=settings.database_schema, include_schemas=True,
            )
        )
        async with connection.begin():
            await connection.run_sync(lambda c: context.run_migrations())
    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio
    asyncio.run(run_migrations_online())

from logging.config import fileConfig
from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from app.core.config import get_settings
from app.database.base import Base
from app.models.user import User  # noqa: F401
from app.models.season import Season  # noqa: F401
from app.features.predictions.models import Prediction, PredictionMatchup, PredictionWeek  # noqa: F401
from app.features.ptgotw.models import PTGWriteup  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        def migrate(connection):
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
        await connection.run_sync(migrate)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio
    asyncio.run(run_async_migrations())

"""Alembic environment — async migrations against PostgreSQL."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.models.base import Base

# Import every model so Base.metadata is populated.
import app.models.cart  # noqa: F401
import app.models.customer  # noqa: F401
import app.models.notification  # noqa: F401
import app.models.order  # noqa: F401
import app.models.outbox  # noqa: F401
import app.models.processed_event  # noqa: F401
import app.models.product  # noqa: F401
import app.models.return_request  # noqa: F401
import app.models.seller  # noqa: F401
import app.models.store_stock  # noqa: F401
import app.models.tryon_event  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout."""
    context.configure(
        url=settings.async_pg_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an async engine."""
    connectable = create_async_engine(settings.async_pg_url)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

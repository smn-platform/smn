"""Studio database — separate async SQLAlchemy engine for workflow data."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from smn.config import settings

# Separate DB from the main SMN database (configurable via env)
_studio_db_url = settings.studio_database_url

studio_engine = create_async_engine(_studio_db_url, echo=settings.debug)
studio_async_session = async_sessionmaker(
    studio_engine, class_=AsyncSession, expire_on_commit=False
)


async def init_studio_db() -> None:
    """Create studio tables. Safe to call repeatedly."""
    from smn.studio.models import StudioBase

    async with studio_engine.begin() as conn:
        await conn.run_sync(StudioBase.metadata.create_all)


async def get_studio_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a studio database session."""
    async with studio_async_session() as session:
        yield session

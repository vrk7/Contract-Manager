from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


settings = get_settings()
connect_args: dict = {}
pool_class = NullPool
url = make_url(settings.database_url)

# Normalize common Postgres shorthand ("postgres+asyncpg") to the SQLAlchemy
# expected dialect name ("postgresql+asyncpg").
if url.drivername.startswith("postgres+") and not url.drivername.startswith("postgresql+"):
    url = url.set(drivername=url.drivername.replace("postgres", "postgresql", 1))
database_url = url.render_as_string(hide_password=False)
if url.drivername.startswith("sqlite"):
    is_memory_db = (url.database in (None, "", ":memory:")) or (url.query.get("mode") == "memory")
    database_path = Path(url.database).expanduser() if url.database else None
    if database_path and not is_memory_db:
        if not database_path.is_absolute():
            database_path = Path.cwd() / database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)

    connect_args = {"check_same_thread": False, "timeout": 30, "isolation_level": "DEFERRED"}
    if is_memory_db:
        pool_class = StaticPool

engine = create_async_engine(
    database_url,
    future=True,
    echo=settings.debug_mode,
    poolclass=pool_class,
    connect_args=connect_args,
)

if settings.database_url.startswith("sqlite") and "mode=memory" not in settings.database_url:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")
        cursor.close()
AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False, autoflush=False, autocommit=False
)


class Base(DeclarativeBase):
    pass


@asynccontextmanager
async def get_session() -> AsyncSession:
    session: AsyncSession = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
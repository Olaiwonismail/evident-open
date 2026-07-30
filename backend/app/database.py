from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    # Render's free Postgres silently drops idle connections, so a pooled
    # connection can be dead by the time a webhook arrives — the save then fails
    # on the first request after a quiet stretch. pre_ping tests each connection
    # before use (reconnecting transparently); recycle retires them before they
    # can go stale in the first place.
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# Columns added after the first release. create_all never ALTERs existing
# tables, so patch them in by hand — idempotently, on every boot.
_ADDED_COLUMNS = [
    ("members", "bank_account_number", "VARCHAR"),
    ("members", "bank_name", "VARCHAR"),
    ("members", "virtual_account_id", "VARCHAR"),
]


async def _ensure_columns(conn):
    for table, column, coltype in _ADDED_COLUMNS:
        try:
            await conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}")
            )
        except Exception:
            # SQLite has no IF NOT EXISTS for ADD COLUMN — try plain, ignore dup
            try:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
            except Exception:
                pass  # column already exists


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_columns(conn)

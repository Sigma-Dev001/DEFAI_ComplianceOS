import os

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from db.models import Base


def _async_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


engine = create_async_engine(_async_url(), echo=False, future=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


_MIGRATIONS = [
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS decisions JSONB",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS reg_snapshot_id VARCHAR",
    """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='transactions'
              AND column_name='rule_references'
              AND data_type='ARRAY'
        ) THEN
            ALTER TABLE transactions
            ALTER COLUMN rule_references TYPE JSONB
            USING to_jsonb(rule_references);
        END IF;
    END$$
    """,
    """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='transactions'
              AND column_name='confidence'
              AND data_type='character varying'
        ) THEN
            ALTER TABLE transactions
            ALTER COLUMN confidence TYPE DOUBLE PRECISION
            USING CASE
                WHEN confidence = 'low' THEN 0.2
                WHEN confidence = 'medium' THEN 0.55
                WHEN confidence = 'high' THEN 0.85
                ELSE 0.5
            END;
        END IF;
    END$$
    """,
]


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.run_sync(Base.metadata.create_all)
        for sql in _MIGRATIONS:
            await conn.exec_driver_sql(sql)

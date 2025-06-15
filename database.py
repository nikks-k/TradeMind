import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import create_engine

load_dotenv()

# ────────────────────────────────────────────────────────────────────────
# Базовый класс для декларативных моделей
Base = declarative_base()

# -----------------------------------------------------------------------
# DSN и движки
DB_DSN = os.getenv(
    "POSTGRES_DSN",
    "postgresql+asyncpg://crypto:secret@postgres:5432/crypto",
)

# ─── асинхронный (asyncpg) ──────────────────────────────────────────────
async_engine = create_async_engine(DB_DSN, echo=False)
AsyncSessionLocal = sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

AsyncSession = AsyncSessionLocal

# ─── синхронный (psycopg) ───────────────────────────────────────────────
sync_engine_dsn = (
    DB_DSN.replace("postgresql+asyncpg", "postgresql+psycopg")
          .replace("localhost", "postgres")
)
sync_engine = create_engine(sync_engine_dsn, echo=False)

# ─── alias для обратной совместимости (rss_listener ждёт `engine`) ───────
engine = async_engine

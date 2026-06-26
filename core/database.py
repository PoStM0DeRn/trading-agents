import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

Base = declarative_base()

_engine = None
_SessionLocal = None
_async_engine = None
_AsyncSessionLocal = None


def get_database_url(config: dict | None = None) -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    if config and "database" in config:
        return config["database"]["url"]
    return "sqlite:///./data/trading_memory.db"


def get_async_database_url(sync_url: str) -> str:
    if sync_url.startswith("sqlite"):
        return sync_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if sync_url.startswith("postgresql://"):
        return sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return sync_url


def init_db(config: dict | None = None):
    global _engine, _SessionLocal, _async_engine, _AsyncSessionLocal

    sync_url = get_database_url(config)
    db_conf = (config or {}).get("database", {})
    pool_size = db_conf.get("pool_size", 5)
    max_overflow = db_conf.get("max_overflow", 10)
    echo = db_conf.get("echo", False)

    _engine = create_engine(
        sync_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        echo=echo,
    )
    _SessionLocal = sessionmaker(bind=_engine)

    async_url = get_async_database_url(sync_url)
    _async_engine = create_async_engine(
        async_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        echo=echo,
    )
    _AsyncSessionLocal = async_sessionmaker(bind=_async_engine)

    return _engine, _SessionLocal


def get_engine():
    if _engine is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _engine


def get_session():
    if _SessionLocal is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _SessionLocal()


def get_async_engine():
    if _async_engine is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _async_engine


def get_async_session():
    if _AsyncSessionLocal is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _AsyncSessionLocal()

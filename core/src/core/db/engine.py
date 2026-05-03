from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy import create_engine, Engine
from sqlalchemy import URL, make_url


def _base_drivername(u: URL) -> str:
    # "postgresql+psycopg2" -> "postgresql"
    return u.drivername.split("+", 1)[0]


def to_async_url(url: str) -> str:
    u = make_url(url)
    return u.set(drivername=f"{_base_drivername(u)}+asyncpg").render_as_string(hide_password=False)


def to_sync_url(url: str) -> str:
    u = make_url(url)
    return u.set(drivername=f"{_base_drivername(u)}+psycopg2").render_as_string(hide_password=False)


def make_sync_engine(database_url: str, **kwargs) -> Engine:
    """Create a synchronous SQLAlchemy engine."""
    return create_engine(to_sync_url(database_url), pool_pre_ping=True, **kwargs)


def make_async_engine(database_url: str, **kwargs) -> AsyncEngine:
    """Create an asynchronous SQLAlchemy engine."""
    return create_async_engine(to_async_url(database_url), pool_pre_ping=True, **kwargs)


def make_async_sessionmaker(engine: AsyncEngine):
    """Create an asynchronous SQLAlchemy sessionmaker."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(bind=engine, expire_on_commit=False)


def make_sync_sessionmaker(engine: Engine):
    """Create a synchronous SQLAlchemy sessionmaker."""
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=engine, expire_on_commit=False)

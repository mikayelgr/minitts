from functools import lru_cache
from typing import cast
from fastapi import FastAPI
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict
import redis.asyncio as redis
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class AppState:
    """
    Application state to hold shared resources like Redis and PostgreSQL connections.
    """

    # redis: redis.ConnectionPool
    # """
    # Redis connection pool.
    # """


class App(FastAPI):
    """
    FastAPI application with typed state.
    """

    state: AppState


def get_state(app: FastAPI) -> AppState:
    """
    Access the app state with proper typing.
    """

    return cast(AppState, app.state)


class EnvSettings(BaseSettings):
    """
    Environment settings for the application.
    """

    # redis_url: RedisDsn
    # """
    # Redis connection URL.
    #  Example: redis://localhost:6379/0
    # """

    database_url: PostgresDsn
    """
    PostgreSQL connection URL.
     Example: postgresql://user:password@localhost/dbname
    """

    # ensure that the settings are loaded from the .env file
    model_config = SettingsConfigDict(env_file=".env")


@lru_cache  # Cache the settings instance to avoid reloading it multiple times
def get_env_settings() -> EnvSettings:
    """
    Get the environment settings.
        This function is cached to ensure that the settings are loaded only once and reused across the application
    """
    return EnvSettings()


# async def acquire_redis(dsn: RedisDsn) -> None:
#     """
#     Acquire a Redis connection pool and test the connection.
#     """

#     pool = redis.ConnectionPool.from_url(str(dsn), max_connections=20)
#     client = redis.Redis(connection_pool=pool)
#     try:
#         await client.ping()  # Test the Redis connection
#         logger.info("Successfully connected to Redis.")
#         return pool  # Return the connection pool to be used by the app state
#     except Exception as e:
#         raise RuntimeError(f"Failed to connect to Redis: {e}")
#     finally:
#         await client.close()  # Close the test Redis client


@asynccontextmanager
async def lifespan(app: App):
    # cfg = get_env_settings()
    # app.state.redis = await acquire_redis(cfg.redis_url)

    yield  # The application will run until it is shut down

    # await app.state.redis.disconnect()  # Properly close the Redis connection pool

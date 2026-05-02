from functools import lru_cache
from typing import cast
from fastapi import FastAPI
from pydantic import PostgresDsn, RedisDsn, AmqpDsn
from pydantic_settings import BaseSettings, SettingsConfigDict
import logging
from contextlib import asynccontextmanager
from celery import Celery

logger = logging.getLogger(__name__)


class AppState:
    """
    Application state to hold shared resources like Redis and PostgreSQL connections.
    """

    celery: Celery


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

    celery_broker_url: AmqpDsn
    """
    RabbitMQ connection URL for Celery.
     Example: amqp://user:password@localhost:5672/vhost
    """

    celery_result_backend_url: RedisDsn
    """
    Redis connection URL for Celery.
     Example: redis://localhost:6379/0
    """

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


@asynccontextmanager
async def lifespan(app: App):
    cfg = get_env_settings()

    app.state.celery = Celery("api", broker=str(cfg.celery_broker_url), backend=str(cfg.celery_result_backend_url))
    # Ensure that the Celery connection is working before starting the application
    app.state.celery.connection().ensure_connection(max_retries=3, timeout=10)
    yield  # The application will run until it is shut down
    app.state.celery.close()  # Clean up the Celery connection when the application is shutting down

from celery import Celery
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import RedisDsn, AmqpDsn, HttpUrl, PostgresDsn
from core.db.engine import make_sync_engine, to_sync_url


class CeleryWorkerConfig(BaseSettings):
    """Configuration for the Celery worker, loaded from environment variables or a .env file."""

    database_url: PostgresDsn
    celery_broker_url: AmqpDsn
    tts_inference_endpoint: HttpUrl
    celery_result_backend_url: RedisDsn
    model_config = SettingsConfigDict(env_file=".env")


# Ensure that the .env file is loaded and the fields are valid before creating the Celery app
settings = CeleryWorkerConfig()

postgres = make_sync_engine(to_sync_url(str(settings.database_url)))
postgres.connect()  # Test the connection to the database at startup, will raise an error if it fails

app = Celery(
    "celeryz",
    broker=str(settings.celery_broker_url),
    backend=str(settings.celery_result_backend_url),
)

app.conf.update(
    task_compression="gzip",
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-acks-late
    task_acks_late=True,
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-reject-on-worker-lost
    task_reject_on_worker_lost=True,
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-create-missing-queues
    task_create_missing_queues=True,
)

from celery import Celery
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import RedisDsn, AmqpDsn


class CeleryWorkerConfig(BaseSettings):
    """Configuration for the Celery worker, loaded from environment variables or a .env file."""

    celery_broker_url: AmqpDsn
    celery_result_backend_url: RedisDsn
    model_config = SettingsConfigDict(env_file=".env")


# Ensure that the .env file is loaded and the fields are valid before creating the Celery app
settings = CeleryWorkerConfig()

app = Celery("tasks", broker=str(settings.celery_broker_url), backend=str(settings.celery_result_backend_url))
app.conf.update(
    task_compression="gzip",
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-acks-late
    task_acks_late=True,
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-reject-on-worker-lost
    task_reject_on_worker_lost=True,
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-create-missing-queues
    task_create_missing_queues=True,
)

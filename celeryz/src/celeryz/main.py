from celery import Celery
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import RedisDsn, AmqpDsn, HttpUrl, PostgresDsn, Field
import logging
from .s3 import create_s3_client
from .pg import create_pg_engine
from core.tasks import JobDefinition
from celery.loaders.base import BaseLoader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CeleryWorkerConfig(BaseSettings):
    """Configuration for the Celery worker, loaded from environment variables or a .env file."""

    tts_inference_endpoint: HttpUrl

    database_url: PostgresDsn
    celery_broker_url: AmqpDsn
    celery_result_backend_url: RedisDsn

    s3_bucket: str = Field(..., min_length=3)
    s3_endpoint_url: HttpUrl
    s3_public_endpoint_url: HttpUrl
    aws_access_key_id: str = Field(..., min_length=1)
    aws_secret_access_key: str = Field(..., min_length=1)

    model_config = SettingsConfigDict(env_file=".env")


# Ensure that the .env file is loaded and the fields are valid before creating the Celery app
settings = CeleryWorkerConfig()
s3_client = create_s3_client(
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    s3_endpoint_url=settings.s3_endpoint_url,
    s3_bucket=settings.s3_bucket,
)
pg_engine = create_pg_engine(settings.database_url)


app = Celery(
    "celeryz",
    broker=str(settings.celery_broker_url),
    backend=str(settings.celery_result_backend_url),
    include=["celeryz.tasks"],
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

# Force import of modules from `include=[...]` before validating registrations.
BaseLoader(app).import_default_modules()


for job in JobDefinition:
    if job.value not in app.tasks:
        raise Exception(
            f"Registered Celery task `{job.value}` not found in Celery app. This task will not be executed."
        )

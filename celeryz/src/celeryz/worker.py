from celery import Celery
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import RedisDsn, AmqpDsn, HttpUrl, PostgresDsn, Field
from core.db.engine import make_sync_engine, to_sync_url
import boto3
import logging
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)


class CeleryWorkerConfig(BaseSettings):
    """Configuration for the Celery worker, loaded from environment variables or a .env file."""

    tts_inference_endpoint: HttpUrl

    database_url: PostgresDsn
    celery_broker_url: AmqpDsn
    celery_result_backend_url: RedisDsn

    s3_bucket: str = Field(..., min_length=3)
    s3_endpoint_url: HttpUrl
    aws_access_key_id: str = Field(..., min_length=1)
    aws_secret_access_key: str = Field(..., min_length=1)

    model_config = SettingsConfigDict(env_file=".env")


# Ensure that the .env file is loaded and the fields are valid before creating the Celery app
settings = CeleryWorkerConfig()
logger = logging.getLogger(__name__)

logger.info("Connecting to Postgres")
postgres = make_sync_engine(to_sync_url(str(settings.database_url)))
postgres.connect()  # Test the connection to the database at startup, will raise an error if it fails
logger.info("Successfully connected to Postgres")

logger.info("Connecting to S3")
aws_session = boto3.Session(
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
)
s3 = aws_session.client("s3", endpoint_url=str(settings.s3_endpoint_url))
try:
    if s3.get_public_access_block(Bucket=settings.s3_bucket)["PublicAccessBlockConfiguration"]["BlockPublicAcls"]:
        # Ensure the bucket is publicly accessible by removing any public access blocks.
        r = s3.delete_public_access_block(Bucket=settings.s3_bucket)
        if r["ResponseMetadata"]["HTTPStatusCode"] >= 200 and r["ResponseMetadata"]["HTTPStatusCode"] < 300:
            logger.info(f"Removed public access block from S3 bucket {settings.s3_bucket}")
        else:
            logger.error(f"Failed to remove public access block from S3 bucket {settings.s3_bucket}: response={r}")
            raise
except ClientError as e:
    if "notimplemented" in str(e).lower():
        logger.warning(
            f"S3 endpoint {settings.s3_endpoint_url} does not support public access block configuration, skipping this step."
        )
    else:
        raise e
logger.info("Connected to S3")


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

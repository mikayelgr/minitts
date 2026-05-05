from typing import cast
from .main import app, s3_client, settings
from core.tasks import JobDefinition
from celery import Task
import logging
from .main import pg_engine
from core.db.engine import make_sync_sessionmaker
from pydantic import validate_call, ConfigDict
from .util import generate_audio, GenerateAudioDeps
from .exc import RetryableError, FatalError

logger = logging.getLogger(__name__)
Session = make_sync_sessionmaker(pg_engine)
# Required to allow the Celery 'Task' object (self) through validation, as well as to ensure
# that the input data strictly adheres to the expected schema without allowing any extra fields
# or types. This is crucial for maintaining data integrity and preventing potential issues during
# task execution.
validation_config = ConfigDict(extra="allow", strict=True, arbitrary_types_allowed=True)


@app.task(
    name=JobDefinition.TTS_REFUND,
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=60 * 10,  # 10 minutes
)
@validate_call(config=validation_config)
def refund_tts_job(self: Task, job_id: str, quota_usage_event_id: str):
    pass  # Implementation of refund logic goes here, e.g., interacting with payment gateway or updating user balance


@app.task(
    name=JobDefinition.TTS_SYNTHESIZE,
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=60 * 30,  # 30 minutes
)
@validate_call(config=validation_config)
def synthesize_audio(self: Task, job_id: str, quota_usage_event_id: str):
    with Session() as session:
        try:
            generate_audio(
                session,
                GenerateAudioDeps(
                    job_id=job_id,
                    retries=cast(int, self.request.retries),
                    max_retries=self.max_retries,
                    s3_client=s3_client,
                    s3_bucket=settings.s3_bucket,
                    s3_endpoint=settings.s3_endpoint_url,
                    tts_inference_endpoint=settings.tts_inference_endpoint,
                ),
            )
        except RetryableError as e:
            raise self.retry(exc=e)
        except FatalError as e:
            # Let Celery enqueue the background refund task on absolute failure
            logger.error(f"Failed to synthesize audio for job={job_id}")
            try:
                cast(Task, refund_tts_job).delay(
                    job_id=job_id,
                    quota_usage_event_id=quota_usage_event_id,
                )
            except Exception as refund_e:
                logger.error(f"Failed to enqueue refund task for job={job_id}: {refund_e}")
                raise self.retry(exc=refund_e, max_retries=self.max_retries + 1)

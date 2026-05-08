from typing import cast

from .main import s3_client, settings
from core.tasks import JobDefinition
from celery import Task, shared_task
import logging
from .main import pg_engine
from core.db.engine import make_sync_sessionmaker
from .util import generate_audio, GenerateAudioDeps, post_job_to_webhook, process_refund
from .exc import RetryableError

logger = logging.getLogger(__name__)
Session = make_sync_sessionmaker(pg_engine)


@shared_task(
    name=JobDefinition.TTS_REFUND,
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=60 * 10,  # 10 minutes
)
def refund_tts_job(self: Task, job_id: str, quota_usage_event_id: int):
    with Session() as session:
        try:
            process_refund(session, job_id, quota_usage_event_id)
        except Exception as e:
            raise self.retry(exc=e)


@shared_task(
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=60 * 10,  # 10 minutes
)
def send_webhook(self: Task, job_id: str):
    with Session() as session:
        try:
            post_job_to_webhook(session, job_id)
        except RetryableError as e:
            session.rollback()
            raise self.retry(exc=e)
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to send webhook for job={job_id}: {e}")
            raise self.retry(exc=e, max_retries=self.max_retries + 1)


@shared_task(
    name=JobDefinition.TTS_SYNTHESIZE,
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=60 * 30,  # 30 minutes
)
def synthesize_audio(self: Task, job_id: str, quota_usage_event_id: int):
    with Session() as session:
        try:
            job = generate_audio(
                session,
                GenerateAudioDeps(
                    job_id=job_id,
                    retries=cast(int, self.request.retries),
                    max_retries=self.max_retries,
                    s3_client=s3_client,
                    s3_bucket=settings.s3_bucket,
                    s3_endpoint=settings.s3_endpoint_url,
                    s3_public_endpoint=settings.s3_public_endpoint_url,
                    tts_inference_endpoint=settings.tts_inference_endpoint,
                ),
            )

            if not job:
                return

            cast(Task, send_webhook).delay(job_id=job.id)
        except RetryableError as e:
            raise self.retry(exc=e)
        except Exception as e:
            # Let Celery enqueue the background refund task on absolute failure
            logger.error(f"Failed to synthesize audio for job={job_id}: exception={e}")
            try:
                cast(Task, refund_tts_job).delay(
                    job_id=job_id,
                    quota_usage_event_id=quota_usage_event_id,
                )
            except Exception as e:
                logger.error(f"Failed to enqueue refund task for job={job_id}: {e}")
                raise self.retry(exc=e, max_retries=self.max_retries + 1)

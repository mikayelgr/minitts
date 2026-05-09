from typing import cast

from .main import s3_client, settings
from core.tasks import JobDefinition
from celery import Task, shared_task
import logging
from .main import pg_engine
from core.db.engine import make_sync_sessionmaker
from .util import generate_and_store_audio, GenerateAudioDeps, post_job_to_webhook, process_refund
from .exc import RetryableError

logger = logging.getLogger(__name__)
Session = make_sync_sessionmaker(pg_engine)


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------
# Every task in this module retries indefinitely on transient failure. The
# rationale is per-task:
#
#   * refund_tts_job  — a dropped refund leaves the user's quota debited for
#                       a job that ultimately failed; they paid for nothing.
#   * send_webhook    — a dropped delivery silently breaks the API contract
#                       with the caller (no completion notification).
#   * synthesize_audio — a dropped synthesis leaves the job in PENDING forever
#                       and the user's quota deduction is never reconciled.
#
# "Indefinite" means there is no attempt cap, but there is still an exponential
# backoff with a per-task ceiling (RETRY_BACKOFF_MAX_*) so a flapping
# downstream cannot tight-loop the worker. Frequency is bounded; attempts are
# not.
#
# Distinction between retryable and absolute failure:
#   * RetryableError  — explicit signal from the inner code that the failure
#                       is transient (HTTP 5xx, connection drop, lock
#                       contention, etc.). Always retried.
#   * Exception       — anything else. In synthesize_audio this is treated as
#                       an absolute failure: the task does NOT retry the
#                       synthesis itself; it instead enqueues refund_tts_job
#                       and exits. (Enqueueing the refund is its own retry
#                       loop — see the inner except.)
#                       In send_webhook and refund_tts_job there is no
#                       refund/escape hatch, so unexpected exceptions are also
#                       retried indefinitely.
# ---------------------------------------------------------------------------

# Backoff ceilings (seconds). Backoff doubles between attempts and clamps here.
RETRY_BACKOFF_MAX_REFUND = 60 * 10   # 10 minutes
RETRY_BACKOFF_MAX_WEBHOOK = 60 * 10  # 10 minutes
RETRY_BACKOFF_MAX_SYNTHESIZE = 60 * 30  # 30 minutes


@shared_task(
    name=JobDefinition.TTS_REFUND,
    bind=True,
    max_retries=None,  # see "Retry policy" above
    retry_backoff=True,
    retry_backoff_max=RETRY_BACKOFF_MAX_REFUND,
)
def refund_tts_job(self: Task, job_id: str, quota_usage_event_id: int):
    with Session() as session:
        try:
            process_refund(session, job_id, quota_usage_event_id)
        except Exception as e:
            # Refunds must not be lost — retry any failure, including unexpected ones.
            raise self.retry(exc=e, max_retries=None)


@shared_task(
    bind=True,
    max_retries=None,  # see "Retry policy" above
    retry_backoff=True,
    retry_backoff_max=RETRY_BACKOFF_MAX_WEBHOOK,
)
def send_webhook(self: Task, job_id: str):
    with Session() as session:
        try:
            post_job_to_webhook(session, job_id)
        except RetryableError as e:
            session.rollback()
            raise self.retry(exc=e, max_retries=None)
        except Exception as e:
            # Webhook delivery must not be lost — retry any failure.
            session.rollback()
            logger.error(f"Failed to send webhook for job={job_id}: {e}")
            raise self.retry(exc=e, max_retries=None)


@shared_task(
    name=JobDefinition.TTS_SYNTHESIZE,
    bind=True,
    max_retries=None,  # see "Retry policy" above
    retry_backoff=True,
    retry_backoff_max=RETRY_BACKOFF_MAX_SYNTHESIZE,
)
def synthesize_audio(self: Task, job_id: str, quota_usage_event_id: int):
    with Session() as session:
        try:
            job = generate_and_store_audio(
                session,
                GenerateAudioDeps(
                    job_id=job_id,
                    s3_client=s3_client,
                    s3_bucket=settings.s3_bucket,
                    s3_public_endpoint=settings.s3_public_endpoint_url,
                    tts_inference_endpoint=settings.tts_inference_endpoint,
                ),
            )

            if not job:
                return

            cast(Task, send_webhook).delay(job_id=str(job.id))
        except RetryableError as e:
            raise self.retry(exc=e, max_retries=None)
        except Exception as e:
            # Absolute failure: don't retry the synthesis itself, refund the user instead.
            logger.error(f"Failed to synthesize audio for job={job_id}: exception={e}")
            try:
                cast(Task, refund_tts_job).delay(
                    job_id=job_id,
                    quota_usage_event_id=quota_usage_event_id,
                )
            except Exception as e:
                # Enqueueing the refund itself failed (broker hiccup) — retry the synthesize task
                # so we get another shot at scheduling the refund. The synthesis itself is
                # idempotent at the row-state level (lock_job_for_processing filters states), so
                # re-running it is safe.
                logger.error(f"Failed to enqueue refund task for job={job_id}: {e}")
                raise self.retry(exc=e, max_retries=None)

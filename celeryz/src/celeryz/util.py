from core.db.models import Job, JobState, User, QuotaUsageEvent, UsageEventType
from core.db.queries.jobs import lock_job_for_processing
import time
from sqlalchemy import select
from botocore.exceptions import ClientError
import logging
from sqlalchemy.orm import Session
from typing import Any, cast
import uuid
from types_boto3_s3 import S3Client
from pydantic import BaseModel, StrictStr, HttpUrl, ConfigDict
from .exc import RetryableError, FatalError
import httpx
from httpx import BasicAuth
from url_normalize import url_normalize
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARN)


class HttpxStreamWrapper:
    def __init__(self, response_iterator):
        self._iterator = response_iterator
        self._buffer = b""

    def read(self, size=-1):
        if size == -1:
            return self._buffer + b"".join(self._iterator)
        while len(self._buffer) < size:
            try:
                self._buffer += next(self._iterator)
            except StopIteration:
                break
        result = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return result


class GenerateAudioDeps(BaseModel):
    job_id: StrictStr
    s3_client: Any  # We use Any here because the S3Client type from types_boto3_s3 is not recognized as a valid type by Pydantic, even though it is the correct type for our S3 client instance.
    s3_bucket: StrictStr
    s3_public_endpoint: HttpUrl
    tts_inference_endpoint: HttpUrl

    # We need to do this since S3Client is recognized as an arbitrary type
    model_config = ConfigDict(arbitrary_types_allowed=True)


def generate_and_store_audio(session: Session, deps: GenerateAudioDeps):
    job_uuid = uuid.UUID(deps.job_id)
    result = lock_job_for_processing(session, job_uuid)
    if result.is_locked:
        # Another transaction holds the row lock (likely a transient API read or a concurrent
        # worker delivery from a redelivered task). Retry instead of silently succeeding —
        # otherwise the synthesis would be skipped and the job would sit in PENDING forever.
        raise RetryableError(f"Job {deps.job_id} is locked by another transaction")
    if not result.job:
        # `lock_job_for_processing` filters by state in (CREATED, PENDING, EXECUTING), so a None
        # result here could mean either: (a) the row genuinely doesn't exist — likely an orphaned
        # task whose submit-side transaction rolled back after Celery accepted the enqueue, or
        # (b) the row exists but is in a terminal state already (SUCCESS / FAILURE — sibling
        # delivery beat us to it, job was cancelled, etc.). Disambiguate so we can log usefully —
        # silent no-ops on case (a) hide a real bug if the rollback path ever starts firing.
        exists = session.execute(select(Job.id).where(Job.id == job_uuid)).scalar_one_or_none()
        if exists is None:
            logger.warning(
                f"Synthesize task received for job_id={deps.job_id} but no row exists in the "
                "database — likely an orphaned enqueue from a rolled-back submit transaction."
            )
        else:
            logger.info(
                f"Synthesize task for job_id={deps.job_id} found the row in a non-eligible state; "
                "skipping (already processed, cancelled, or claimed by a sibling delivery)."
            )
        return None

    job = result.job

    job.state = JobState.EXECUTING
    job.started_at = datetime.now(timezone.utc)
    session.commit()

    file_key = f"{job.id}__{time.monotonic_ns()}.wav"
    s3_client = cast(S3Client, deps.s3_client)

    try:
        with httpx.stream(
            "POST",
            str(deps.tts_inference_endpoint),
            data=job.text,
            auth=BasicAuth(username=job.user.username, password=str(len(job.user.username))),
        ) as response:
            if response.status_code != 200:
                # Any non-200 from the inference endpoint is treated as transient and surfaced as
                # RetryableError. The synthesize task retries on that exception with no upper
                # bound (see celeryz.tasks docstring), so this branch never marks the job FAILURE
                # on its own — only an unexpected exception in the calling task does, via
                # mark_job_failed alongside the refund enqueue.
                logger.warning(f"Received non-200 response for job={job.id} status={response.status_code}")
                job.state = JobState.PENDING
                job.error = f"Received non-200 response: {response.status_code}. Retrying..."
                session.commit()
                raise RetryableError(f"Non-200 response: {response.status_code}")

            try:
                s3_client.upload_fileobj(
                    Bucket=deps.s3_bucket,
                    Key=file_key,
                    # Stream the response in chunks of size 1MB to avoid loading the entire audio file into memory at once. This is
                    # important for handling large audio files without running into memory issues. We place the stress more on the
                    # network and disk I/O rather than memory, which is more efficient for large files.
                    Fileobj=HttpxStreamWrapper(response.iter_bytes(chunk_size=1024**2)),
                    ExtraArgs={"ContentType": "audio/wav"},
                )

                r = s3_client.get_object_attributes(
                    Bucket=deps.s3_bucket, Key=file_key, ObjectAttributes=["ObjectSize"]
                )
                # Sample rate of Soprano is 32kHz. We calculate the duration in seconds using the formula
                # file_size / (sample_rate * bytes_per_sample * channels)
                job.duration_seconds = r["ObjectSize"] / (32000 * 2 * 1)
                s3_client.put_object_acl(Bucket=deps.s3_bucket, Key=file_key, ACL="public-read")
            except ClientError as e:
                logger.error(f"Error occurred while uploading to S3: {e}")
                job.state = JobState.PENDING
                job.error = f"Failed to upload audio to S3: {str(e)}"
                session.commit()
                try:
                    s3_client.delete_object(Bucket=deps.s3_bucket, Key=file_key)
                except Exception as cleanup_error:
                    logger.error(
                        f"Error occurred while cleaning up partial S3 upload for job={job.id}: {cleanup_error}"
                    )

                raise RetryableError(str(e))
    except httpx.RequestError as e:
        # Connection-layer failures (DNS, connect, TLS, read timeout while streaming). These never
        # reach the status-code branch above, so without this handler they'd bubble out of the task
        # as an unclassified Exception and trigger an immediate refund without any retry.
        logger.warning(f"Connection error talking to TTS inference endpoint for job={job.id}: {e}")
        job.state = JobState.PENDING
        job.error = f"Connection error: {e}"
        session.commit()
        raise RetryableError(f"Connection error: {e}")

    job.audio_url = url_normalize(f"{deps.s3_public_endpoint}/{deps.s3_bucket}/{file_key}")
    job.state = JobState.SUCCESS
    job.completed_at = datetime.now(timezone.utc)
    job.error = None
    session.commit()
    return job


def post_job_to_webhook(session: Session, job_id: str):
    try:
        stmt = select(Job).filter(Job.id == job_id).with_for_update(skip_locked=True)
        job = session.execute(stmt).scalar_one_or_none()
        if not job:
            logger.error(f"Job with id={job_id} not found for webhook posting")
            raise FatalError(f"Job with id={job_id} not found")

        # Persist the attempt time alongside the attempt counter so webhook_delivered_at reflects
        # the most recent attempt — including failed ones. Otherwise the field would stay NULL
        # until the first successful delivery, which loses information about prior tries.
        job.webhook_attempts += 1
        job.webhook_delivered_at = datetime.now(timezone.utc)
        session.commit()

        response = httpx.post(str(job.callback_url), json=job.model_dump(mode="json"))
        response.raise_for_status()
    except httpx.RequestError as e:
        logger.error(f"HTTP request error when posting to webhook for job={job_id}: {e}")
        raise RetryableError(f"HTTP request error: {e}")
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        # 4xx (other than 408 Request Timeout and 429 Too Many Requests) are client errors that
        # won't be fixed by retrying — bad URL, auth rejection, gone, etc. Treat them as fatal so
        # we don't burn the retry budget on them. 5xx and the two retryable 4xx codes still retry.
        if 400 <= status < 500 and status not in (408, 429):
            logger.error(f"Fatal HTTP status {status} from webhook for job={job_id}: {e}")
            raise FatalError(f"Webhook returned non-retryable status: {status}")
        logger.error(f"Retryable HTTP status {status} from webhook for job={job_id}: {e}")
        raise RetryableError(f"HTTP status error: {e}")


def mark_job_failed(session: Session, job_id: str, error: str) -> None:
    """Transition a job to FAILURE during the absolute-failure path of synthesize_audio.

    Caller is expected to rollback any in-flight transaction on the session before calling
    this — the synthesize except path may unwind mid-transaction and any uncommitted state
    would otherwise be flushed alongside the FAILURE write. Idempotent on jobs already in a
    terminal state (SUCCESS / FAILURE) — those are left untouched.
    """
    job = session.execute(select(Job).where(Job.id == uuid.UUID(job_id))).scalar_one_or_none()
    if job is None:
        logger.warning(f"mark_job_failed: job_id={job_id} not found; nothing to mark")
        return
    if job.state in (JobState.SUCCESS, JobState.FAILURE):
        return
    job.state = JobState.FAILURE
    job.error = error
    job.completed_at = datetime.now(timezone.utc)
    session.commit()


def process_refund(session: Session, job_id: str, quota_usage_event_id: int):
    try:
        # Lock the original USAGE event for the duration of the transaction so two concurrent
        # refund tasks for the same job serialize on it. Otherwise both can pass the
        # `existing_refund is None` check and both insert a refund row, double-crediting the user.
        original_event = session.execute(
            select(QuotaUsageEvent).with_for_update().where(QuotaUsageEvent.id == quota_usage_event_id)
        ).scalar_one_or_none()

        if not original_event:
            logger.error(f"Quota usage event {quota_usage_event_id} not found for job {job_id}")
            return

        existing_refund = session.execute(
            select(QuotaUsageEvent).where(
                QuotaUsageEvent.job_id == uuid.UUID(job_id), QuotaUsageEvent.event_type == UsageEventType.REFUND
            )
        ).scalar_one_or_none()

        if existing_refund:
            logger.warning(f"Refund already processed for job {job_id}")
            return

        user = session.execute(select(User).with_for_update().where(User.id == original_event.user_id)).scalar_one()

        refund_event = QuotaUsageEvent(
            amount=original_event.amount,
            event_type=UsageEventType.REFUND,
            job_id=original_event.job_id,
            user_id=original_event.user_id,
        )
        session.add(refund_event)

        user.quota_tokens_remaining += original_event.amount

        session.commit()
        logger.info(f"Successfully refunded {original_event.amount} characters for job {job_id} to user {user.id}")

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to refund job={job_id}: {e}")
        raise e

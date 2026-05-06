from core.db.models import Job, JobState, User, QuotaUsageEvent, UsageEventType
from core.db.queries.jobs import lock_job_for_processing
import time
from sqlalchemy import func, select
from botocore.exceptions import ClientError
import logging
from sqlalchemy.orm import Session
from typing import Any, cast
import uuid
from types_boto3_s3 import S3Client
from pydantic import BaseModel, StrictStr, StrictInt, HttpUrl, ConfigDict
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
    retries: StrictInt
    max_retries: StrictInt
    s3_client: Any  # We use Any here because the S3Client type from types_boto3_s3 is not recognized as a valid type by Pydantic, even though it is the correct type for our S3 client instance.
    s3_bucket: StrictStr
    s3_endpoint: HttpUrl
    s3_public_endpoint: HttpUrl
    tts_inference_endpoint: HttpUrl

    # We need to do this since S3Client is recognized as an arbitrary type
    model_config = ConfigDict(arbitrary_types_allowed=True)


def generate_audio(session: Session, deps: GenerateAudioDeps):
    job = lock_job_for_processing(session, job_id=deps.job_id)
    if not job:
        return None  # Already being processed

    job.state = JobState.EXECUTING
    job.started_at = datetime.now(timezone.utc)
    session.commit()

    with httpx.stream(
        "POST",
        str(deps.tts_inference_endpoint),
        data=job.text,
        auth=BasicAuth(username=job.user.username, password=str(len(job.user.username))),
    ) as response:
        if response.status_code != 200:
            logger.warning(f"Received non-200 response for job={job.id} status={response.status_code}")
            if deps.retries < deps.max_retries:
                job.state = JobState.PENDING
                job.error = f"Received non-200 response: {response.status_code}. Retrying..."
                session.commit()
                raise RetryableError(f"Non-200 response: {response.status_code}")
            else:
                job.state = JobState.FAILURE
                job.error = f"Failed to synthesize audio after {deps.max_retries} attempts. Last status code: {response.status_code}"
                session.commit()
                raise FatalError("Max retries exhausted")

        file_key = f"{job.id}__{time.monotonic_ns()}.wav"
        s3_client = cast(S3Client, deps.s3_client)

        try:
            s3_client.upload_fileobj(
                Bucket=deps.s3_bucket,
                Key=file_key,
                # Stream the response in chunks of size 16KB to avoid loading the entire audio file into memory at once. This is
                # important for handling large audio files without running into memory issues. We place the stress more on the
                # network and disk I/O rather than memory, which is more efficient for large files.
                Fileobj=HttpxStreamWrapper(response.iter_bytes(chunk_size=16 * 1024)),
                # Ensure that the object is publicly readable with its URL (this is necessary for the callback to access the file without
                # needing AWS credentials). We set the ACL to "public-read" which allows anyone to read the object, but does not allow public
                # write access.
                ExtraArgs={"ContentType": "audio/wav"},
            )

            r = s3_client.get_object_attributes(Bucket=deps.s3_bucket, Key=file_key, ObjectAttributes=["ObjectSize"])
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
                logger.error(f"Error occurred while cleaning up partial S3 upload for job={job.id}: {cleanup_error}")
                pass  # If cleanup fails, we log it but do not raise an exception since the main error is the upload failure

            raise RetryableError(str(e))

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

        job.webhook_attempts += 1
        session.commit()

        response = httpx.post(str(job.callback_url), json=job.model_dump(mode="json"))
        response.raise_for_status()

        job.webhook_delivered_at = datetime.now(timezone.utc)
        session.commit()
    except httpx.RequestError as e:
        logger.error(f"HTTP request error when posting to webhook for job={job_id}: {e}")
        raise RetryableError(f"HTTP request error: {e}")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP status error when posting to webhook for job={job_id}: {e}")
        raise RetryableError(f"HTTP status error: {e}")


def process_refund(session: Session, job_id: str, quota_usage_event_id: int):
    try:
        original_event = session.execute(
            select(QuotaUsageEvent).where(QuotaUsageEvent.id == quota_usage_event_id)
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
        logger.info(f"Successfully refunded {original_event.amount} tokens for job {job_id} to user {user.id}")

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to refund job={job_id}: {e}")
        raise e

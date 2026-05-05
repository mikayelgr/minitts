from core.db.models import JobState
from core.db.queries.jobs import lock_job_for_processing
from pyreqwest.simple.sync_request import pyreqwest_post
import time
from sqlalchemy import func
from botocore.exceptions import ClientError
import logging
from sqlalchemy.orm import Session
from types_boto3_s3 import S3Client
from pydantic import BaseModel, StrictStr, StrictInt, HttpUrl
from .exc import RetryableError, FatalError

logger = logging.getLogger(__name__)


class GenerateAudioDeps(BaseModel):
    job_id: StrictStr
    retries: StrictInt
    max_retries: StrictInt
    s3_client: S3Client
    s3_bucket: StrictStr
    s3_endpoint: HttpUrl
    tts_inference_endpoint: StrictStr


def generate_audio(session: Session, deps: GenerateAudioDeps):
    job = lock_job_for_processing(session, job_id=deps.job_id)
    if not job:
        return None  # Already being processed

    job.state = JobState.EXECUTING
    job.started_at = func.now()
    session.commit()

    request = (
        pyreqwest_post(deps.tts_inference_endpoint)
        .basic_auth(job.user.username, str(len(job.user.username)))
        .body_text(job.text)
    )

    response = request.send()
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

    response_body = response.body_reader
    file_key = f"{job.id}-{time.monotonic_ns()}.wav"
    try:
        deps.s3_client.put_object(
            Bucket=deps.s3_bucket,
            Key=file_key,
            Body=response_body,
            ContentType="audio/wav",
            ACL="public-read",
        )
    except ClientError as e:
        logger.error(f"Error occurred while uploading to S3: {e}")
        job.state = JobState.PENDING
        job.error = f"Failed to upload audio to S3: {str(e)}"
        session.commit()
        try:
            deps.s3_client.delete_object(Bucket=deps.s3_bucket, Key=file_key)
        except Exception as cleanup_error:
            logger.error(f"Error occurred while cleaning up partial S3 upload for job={job.id}: {cleanup_error}")
            pass  # If cleanup fails, we log it but do not raise an exception since the main error is the upload failure

        raise RetryableError(str(e))

    job.audio_url = f"{deps.s3_endpoint}/{deps.s3_bucket}/{file_key}"
    job.state = JobState.SUCCESS
    job.completed_at = func.now()
    job.error = None
    session.commit()
    return job

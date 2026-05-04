from .worker import app, settings, s3
from core.tasks import JobDefinition
from core.db.models import JobState
from core.db.queries.jobs import lock_job_for_processing
from celery import Task
from pyreqwest.simple.sync_request import pyreqwest_post
import logging
from .worker import postgres
from core.db.engine import make_sync_sessionmaker
from typing import cast
from pydantic import validate_call, StrictInt, ConfigDict
import time
from sqlalchemy import func
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
Session = make_sync_sessionmaker(postgres)
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
def refund_tts_job(self: Task, job_id: StrictInt, user_id: StrictInt, amount: StrictInt):
    # Placeholder for refund logic
    logger.info(f"Refunding TTS job with id={job_id}")
    # Implement refund logic here, e.g., update job status, process payment refund, etc.


@app.task(
    name=JobDefinition.TTS_SYNTHESIZE,
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=60 * 30,  # 30 minutes
)
@validate_call(config=validation_config)
def synthesize_audio(self: Task, job_id: str):
    with Session() as session:
        # Attempt to lock the job for processing. If the job is already being processed by another worker,
        # we log a warning and exit gracefully.
        job = lock_job_for_processing(session, job_id=job_id)
        if not job:
            logger.warning(f"Job with id={job_id} is already being processed by another worker.")
            return

        job.state = JobState.EXECUTING
        job.started_at = func.now()
        session.commit()

        request = (
            pyreqwest_post(settings.tts_inference_endpoint)
            .basic_auth(
                job.user.username,
                str(len(job.user.username)),
            )
            .body_text(job.text)
        )

        response = request.send()  # Sending the request, which should return a streaming response
        if response.status_code != 200:
            logger.warning(f"Received non-200 response for job={job.id} status={response.status_code}")
            # If we have not yet exhausted our retry attempts, we raise a retry exception to have Celery
            # automatically retry the task after a backoff period.
            if self.request.retries < self.max_retries:
                logger.info(f"Retrying job={job.id} attempt={self.request.retries + 1}")
                job.state = JobState.PENDING
                job.error = f"Received non-200 response: {response.status_code}. Retrying..."
                session.commit()
                raise self.retry(exc=Exception(f"Non-200 response: {response.status_code}"))

            # If we have exhausted all retry attempts, we update the job state to FAILURE and log an error.
            job.state = JobState.FAILURE
            job.error = f"Failed to synthesize audio after {self.max_retries} attempts. Last status code: {response.status_code}"
            # If we have exhausted all retry attempts, we log an error and refund the job in the background.
            logger.error(f"Failed to synthesize audio for job={job.id}")

            try:
                # If the synthesis fails, we attempt to refund the job. However, since we are in a
                # synchronous context and cannot await the refund task, we use Celery's `delay`
                # method to enqueue the refund task asynchronously.
                #
                # TODO: Update the function to refund the actual amount of quota tokens consumed by the
                # job, rather than a hardcoded value.
                cast(Task, refund_tts_job).delay(job.id, job.user.id, amount=100)
                session.commit()
                return
            except Exception as e:
                logger.error(f"Failed to enqueue refund task for job={job.id}: {e}")
                job.state = JobState.PENDING  # so retry can re-lock it
                session.commit()
                raise self.retry(exc=e, max_retries=self.max_retries + 1)

        response_body = response.body_reader  # The response body is a stream of audio data
        file_key = f"{job.id}-{time.monotonic_ns()}.wav"
        try:
            # Adding the synthesized audio data to S3.
            s3.put_object(
                Bucket=settings.s3_bucket,
                # Storing the audio file with a unique key that includes the job ID and a timestamp
                # for increased collision resistance.
                Key=file_key,
                Body=response_body,  # The response body is a stream of audio data
                ContentType="audio/wav",
                ACL="public-read",
            )
        except ClientError as e:
            logger.error(f"Error occurred while uploading to S3: {e}")
            # Updating the job state to PENDING to mark that the job hasn't been processed yet.
            job.state = JobState.PENDING
            job.error = f"Failed to upload audio to S3: {str(e)}"
            session.commit()
            try:
                s3.delete_object(Bucket=settings.s3_bucket, Key=file_key)  # Clean up any partial uploads
            except Exception as cleanup_error:
                logger.error(f"Error occurred while cleaning up partial S3 upload for job={job.id}: {cleanup_error}")
                pass  # If cleanup fails, we log it but do not raise an exception since the main error is the upload failure
            raise self.retry(exc=e)

        job.audio_url = f"{settings.s3_endpoint_url}/{settings.s3_bucket}/{file_key}"
        job.state = JobState.SUCCESS
        job.completed_at = func.now()
        job.error = None  # Clear any previous error messages if the job eventually succeeds after retries
        session.commit()

        # Finally post the webhook callback to the client with the audio URL and job details.
        pass

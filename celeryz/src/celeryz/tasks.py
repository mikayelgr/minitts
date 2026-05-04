from .worker import app, settings
from core.tasks import JobDefinition
from core.db.models import Job, JobState
from celery import Task
from pyreqwest.simple.sync_request import pyreqwest_post
import logging
from .worker import postgres
from core.db.engine import make_sync_sessionmaker
from sqlalchemy import update
from pydantic import ValidationError
from typing import cast
from pydantic import validate_call, StrictInt, ConfigDict

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
def synthesize_audio(self: Task, job: dict):
    try:
        # Ensuring that the input dictionary strictly adheres to the Job model schema
        # before processing the task.
        job: Job = Job.model_validate(job, strict=True, extra="forbid")
    except ValidationError as e:
        # Since we cannot possibly extract any job information from the invalid data,
        # we log the error and raise an exception to indicate that the task cannot be
        # processed even if we wanted to refund it, as we don't have a valid job ID or
        # user information.
        logger.error(f"Validation error for job data: {e}")
        raise ValueError("Invalid job data provided") from e

    if job.state != JobState.PENDING:
        stmt = (
            update(Job)
            .where(Job.id == job.id, Job.state != JobState.PENDING, Job.user_id == job.user_id)
            .values(state=JobState.PENDING)
        )
        with Session() as session:
            session.execute(stmt)
            session.commit()
            session.refresh(job)

    request = (
        pyreqwest_post(settings.tts_inference_endpoint)
        .basic_auth(
            job.user.username,
            str(len(job.user.username)),
        )
        .body_text(job.text)
    )

    response = request.send()
    if response.status_code != 200:
        logging.warning(f"Received non-200 response for job={job.id} status={response.status_code}")
        if self.request.retries < self.max_retries:
            logging.info(f"Retrying job={job.id} attempt={self.request.retries + 1}")
            raise self.retry()
        else:
            logger.error(f"Failed to synthesize audio for job={job.id}")
            # If the synthesis fails, we attempt to refund the job. However, since we are in a
            # synchronous context and cannot await the refund task, we use Celery's `delay`
            # method to enqueue the refund task asynchronously.
            cast(Task, refund_tts_job).delay(job.id, job.user.id, amount=100)
            raise

    with Session() as session:
        pass
        # Process the successful response by storing the audio data from the stream into SeaweedFS
        # and updating the job record in the database with the URL of the stored audio file.
        # TODO: Not yet implemented.

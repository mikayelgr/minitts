from sqlalchemy import select
from sqlalchemy.exc import DataError
from sqlalchemy.orm.session import Session
from sqlalchemy.ext.asyncio import AsyncSession
from core.db.models import Job, User, JobState
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


async def create_job(session: AsyncSession, user: User, partial_job: Job) -> Job:
    job = Job(
        **partial_job.model_dump(exclude_unset=True),
        user_id=user.id,
        state=JobState.CREATED,
    )

    session.add(job)
    return job


def lock_job_for_processing(session: Session, job_id: UUID) -> Job | None:
    # Attempt to lock the job for processing. If the job is already being processed by another worker,
    # we return None to indicate that this worker should not process the job.
    stmt = (
        select(Job)
        .with_for_update(skip_locked=True)
        .where(
            Job.id == job_id,
            Job.state.in_([JobState.CREATED, JobState.PENDING]),
        )
        .limit(1)
    )
    try:
        # At this point if a job exists it is now locked for processing. One failure point here
        # is if the user passes a string which is not a valid UUID which can cause an exception
        # so we must ensure that we handle it properly.
        job = session.execute(stmt).scalar_one_or_none()
        return job
    except DataError as e:
        # In case the user provided an invalid UUID string, we return none early
        return None
    except Exception as e:
        logger.error(f"Unexpected error while locking job with id={job_id} for processing: {e}")
        return None


async def get_job_unlocked(session: AsyncSession, job_id: UUID) -> Job | None:
    stmt = select(Job).where(Job.id == job_id).with_for_update(nowait=True)
    try:
        job = await session.execute(stmt)
        return job.scalar_one_or_none()
    except DataError:
        return None

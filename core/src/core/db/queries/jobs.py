from sqlalchemy import update
from sqlalchemy.orm.session import Session
from sqlalchemy.ext.asyncio import AsyncSession
from core.db.models import Job, User, JobState
from sqlmodel import func, update, select
from uuid import UUID


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
    job = session.execute(stmt).scalar_one_or_none()  # At this point if a job exists it is now locked for processing
    if job is None:
        return None

    return job

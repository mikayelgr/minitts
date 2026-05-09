from sqlalchemy import select
from sqlalchemy.exc import DataError, OperationalError
from sqlalchemy.orm.session import Session
from sqlalchemy.ext.asyncio import AsyncSession
from core.db.models import Job, User, JobState
from uuid import UUID
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


async def create_job(session: AsyncSession, user: User, partial_job: Job) -> Job:
    """Creates a new job in the database with the provided user and partial job data."""

    job = Job(
        **partial_job.model_dump(exclude_unset=True),
        user_id=user.id,
        state=JobState.CREATED,
    )

    session.add(job)
    return job


@dataclass
class JobAccessResult:
    """Result of attempting to access a job, distinguishing between not found and locked states."""

    job: Job | None = None
    is_locked: bool = False


def lock_job_for_processing(session: Session, job_id: UUID) -> JobAccessResult:
    """Attempt to lock a job for processing with nowait semantics.

    Uses nowait=True to explicitly raise OperationalError if the job exists but is locked,
    allowing us to distinguish between "not found", "locked", and "successfully locked".

    Returns:
        JobAccessResult with the job if successfully locked, or is_locked=True if locked/unavailable.
    """

    stmt = (
        select(Job)
        .with_for_update(nowait=True)
        .where(
            Job.id == job_id,
            Job.state.in_([JobState.CREATED, JobState.PENDING]),
        )
        .limit(1)
    )
    try:
        job = session.execute(stmt).scalar_one_or_none()
        return JobAccessResult(job=job, is_locked=False)
    except DataError:
        # Invalid UUID format - job not found
        return JobAccessResult(job=None, is_locked=False)
    except OperationalError:
        # Job exists but is locked by another transaction
        return JobAccessResult(job=None, is_locked=True)


async def get_job_safe(session: AsyncSession, job_id: UUID) -> JobAccessResult:
    """Safely fetch a job with a row lock, distinguishing between not found and locked states.

    Returns:
        JobAccessResult with either the job, or is_locked=True if locked.
    """

    stmt = select(Job).where(Job.id == job_id).with_for_update(nowait=True).limit(1)
    try:
        job = await session.execute(stmt)
        return JobAccessResult(job=job.scalar_one_or_none(), is_locked=False)
    except DataError:
        # Invalid UUID format
        return JobAccessResult(job=None, is_locked=False)
    except OperationalError:
        # Job exists but is locked
        return JobAccessResult(job=None, is_locked=True)


async def get_job(session: AsyncSession, job_id: UUID) -> Job | None:
    """Fetch a job without acquiring a row lock. Suitable for read-only status checks
    that must not contend with workers holding the row lock during processing."""

    stmt = select(Job).where(Job.id == job_id).limit(1)
    try:
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except DataError:
        return None

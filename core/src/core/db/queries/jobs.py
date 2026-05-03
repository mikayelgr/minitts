from sqlalchemy.ext.asyncio import AsyncSession
from core.db.models import Job, User


async def create_job(session: AsyncSession, user: User, partial_job: Job) -> Job:
    job = Job(**partial_job.model_dump(exclude_unset=True), user_id=user.id)
    session.add(job)
    return job

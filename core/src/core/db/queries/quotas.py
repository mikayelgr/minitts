from core.db.models import QuotaUsageEvent, UsageEventType, User, Job
from sqlalchemy.ext.asyncio import AsyncSession


async def create_quota_usage_event(
    session: AsyncSession, user: User, job: Job, amount: int, event_type: UsageEventType
) -> QuotaUsageEvent:
    """
    Creates a new QuotaUsageEvent record in the database.

    Args:
        session (AsyncSession): The database session to use for the operation.
        user (User): The user associated with the quota usage event.
        job (Job): The job associated with the quota usage event.
        amount (int): The number of quota units (characters) consumed or refunded.
        event_type (UsageEventType): The type of the event, either USAGE or REFUND.

    Returns:
        QuotaUsageEvent: The created QuotaUsageEvent instance.
    """
    quota_usage_event = QuotaUsageEvent(
        user_id=user.id,
        job_id=job.id,
        amount=amount,
        event_type=event_type,
    )
    session.add(quota_usage_event)
    return quota_usage_event

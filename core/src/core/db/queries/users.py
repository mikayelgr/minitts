from uuid import UUID

from core.db.models import User
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


async def get_or_create_user(session: AsyncSession, username: str) -> User:
    """
    Atomically gets an existing user by username or creates a new one.
    Race-safe via Postgres ON CONFLICT.
    """
    stmt = insert(User).values(username=username).on_conflict_do_nothing(index_elements=["username"]).returning(User)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    # If insert was a no-op (someone else won the race), fetch the existing row.
    if user is None:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one()

    return user


async def lock_user(session: AsyncSession, user_id: UUID) -> User | None:
    """Fetch the user row with FOR UPDATE so concurrent quota mutations are serialized.
    The lock is released when the surrounding transaction commits or rolls back."""
    stmt = select(User).where(User.id == user_id).with_for_update().limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

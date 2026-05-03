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

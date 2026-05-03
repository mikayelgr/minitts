from typing import AsyncGenerator
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_state, AppState


async def get_pg_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides an AsyncSession for database operations.
    Ensures that the session is properly committed or rolled back and
    closed after use.

    Usage in route:
        @router.get("/example")
        async def my_route(session: AsyncSession = Depends(get_pg_session)):
            # Use session here
            pass
    """

    app_state: AppState = get_state(request.app)
    async with app_state.pg_sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi import Depends, HTTPException
from http import HTTPStatus
from app.dependencies import get_pg_session, AsyncSession
from core.db.models import User
from sqlalchemy import select
import logging
from typing import Annotated

security = HTTPBasic()
logger = logging.getLogger(__name__)


async def authenticate(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
    pg: Annotated[AsyncSession, Depends(get_pg_session)],
):
    """
    A simple authentication dependency that only allows access to users with any username
    and specific password which is equal to the length of the username. This is for
    demonstration purposes only.
    """
    expected_password = str(len(credentials.username))
    if credentials.password != expected_password:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Check if the user exists in the database, if not create it
    result = await pg.execute(select(User).where(User.username == credentials.username))
    user = result.scalars().first()
    if not user:
        user = User(username=credentials.username)
        pg.add(user)
        await pg.commit()
        logger.info(f"Created new user: {credentials.username}")
        await pg.refresh(user)  # doing this to get the generated ID from the database
        logger.info(f"User ID: {user.id}")

    return user

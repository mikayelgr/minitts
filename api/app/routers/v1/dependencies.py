from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi import Depends, HTTPException
from http import HTTPStatus
from app.dependencies import get_pg_session, AsyncSession
import core.db.queries.users
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

    user = await core.db.queries.users.get_or_create_user(pg, credentials.username)
    await pg.commit()  # Commit the transaction to save the user if it was created
    return user

import redis.asyncio as redis
from fastapi import Request
from typing import AsyncGenerator
from .config import get_state


async def get_redis(request: Request) -> AsyncGenerator[redis.Redis, None]:
    """
    Dependency to get a Redis connection from the connection pool. Since
    connections are reused across the pool, it's more efficient to not close
    this at the request-level.
    """
    return redis.Redis(connection_pool=get_state(request.app).redis)

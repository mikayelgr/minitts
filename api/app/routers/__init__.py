from fastapi import APIRouter
from . import health

# this is the root router that will include all other routers
router = APIRouter()

# adding the health check router to the root router before attaching anything else
router.include_router(health.router, tags=["health"])

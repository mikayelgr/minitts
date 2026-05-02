from fastapi import APIRouter
from . import tts

router = APIRouter(prefix="/v1")
router.include_router(tts.router)

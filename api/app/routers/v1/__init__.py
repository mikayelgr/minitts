from fastapi import APIRouter, Depends
from . import tts
from .dependencies import authenticate

# All endpoints under the /v1 prefix will require basic authentication with an arbitrary
# username and a password is only correct when its value is equal to the lenght of the
# username string. This is just for demonstration purposes.
router = APIRouter(prefix="/v1", dependencies=[Depends(authenticate)])

router.include_router(tts.router, tags=["tts"])

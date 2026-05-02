from fastapi import APIRouter, Response

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Health check endpoint to verify that the service is running.
    """

    return {"status": "ok"}

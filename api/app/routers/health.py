from fastapi import APIRouter, Response

router = APIRouter()


@router.get("/health")
async def health_check() -> Response:
    """
    Health check endpoint to verify that the service is running.
    """

    return Response("OK", status_code=200)

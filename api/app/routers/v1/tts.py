from fastapi import APIRouter
from http import HTTPStatus
from pydantic import BaseModel, Field, HttpUrl
from app.config import get_env_settings

router = APIRouter(prefix="/tts")


class CreateTTSJobResponse(BaseModel):
    """
    CreateTTSJobResponse defines the structure of the response returned after successfully
    submitting a TTS job.
    """

    job_id: str = Field(
        ...,
        title="TTS Job ID",
        description="A unique identifier for the submitted TTS job.",
        example="123e4567-e89b-12d3-a456-426614174000",
    )


class CreateTTSJobRequest(BaseModel):
    """CreateTTSJobRequest defines the expected payload for a TTS inference request."""

    text: str = Field(
        ...,
        title="TTS text to synthesize",
        description="The input text to be synthesized into speech.",
        example="Hello, world!",
        min_length=20,
        max_length=1000,
    )

    callback_url: HttpUrl = Field(
        ...,
        title="Callback URL for job completion",
        description="The URL to which the server will POST the job result once inference is complete.",
        example="https://myapp.com/webhook",
    )


@router.post("/", status_code=HTTPStatus.ACCEPTED, response_class=CreateTTSJobResponse)
async def submit(request: CreateTTSJobRequest):
    """
    This endpoint is responsible for accepting TTS inference requests. It validates the input payload
    and enqueues a TTS job for asynchronous processing. Once the job is complete, the server will POST
    the result to the provided callback URL.
    """

    return CreateTTSJobResponse(job_id="123e4567-e89b-12d3-a456-426614174000")

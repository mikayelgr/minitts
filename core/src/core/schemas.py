from pydantic import BaseModel, Field, HttpUrl
from uuid import UUID
from typing import Optional
from .tasks import TaskState


class TTSJobPayload(BaseModel):
    """Schema for the payload of a TTS job."""

    job_id: UUID = Field(..., description="Unique identifier for the TTS job")
    text: str = Field(..., description="The text to be synthesized into speech")
    callback_url: HttpUrl = Field(..., description="URL to send the synthesized audio back to once the job is complete")


class TTSJobResult(BaseModel):
    """
    What the worker returns when it's done. Stored in the Celery result
    backend; also the basis for the webhook payload below.
    """

    job_id: UUID = Field(..., description="Unique identifier for the TTS job")
    state: TaskState = Field(..., description="The current state of the TTS job")
    audio_bytes_total: Optional[int] = Field(None, description="Total number of bytes in the synthesized audio")
    duration_seconds: Optional[float] = Field(None, description="Duration of the synthesized audio in seconds")
    error: Optional[str] = Field(None, description="Error message if the job failed")


class TTSWebhookPayload(BaseModel):
    """Schema for the payload sent to the callback URL when a TTS job is complete."""

    job_id: UUID = Field(..., description="Unique identifier for the TTS job")
    state: TaskState = Field(..., description="The final state of the TTS job")
    audio_url: Optional[HttpUrl] = Field(
        None, description="URL where the synthesized audio can be downloaded (present if state is SUCCESS)"
    )
    error: Optional[str] = Field(None, description="Error message if the job failed (present if state is FAILURE)")

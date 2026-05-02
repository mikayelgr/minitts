from . import TaskContract
from pydantic import BaseModel, HttpUrl
from uuid import UUID


class TTSSynthesizePayload(BaseModel):
    """
    Payload for the TTS synthesis task.
    """

    job_id: UUID
    text: str
    callback_url: HttpUrl


class TTSSynthesizeResult(BaseModel):
    """
    Result for the TTS synthesis task.
    """

    job_id: UUID
    audio_url: HttpUrl
    duration_seconds: float


class TTSSynthesizeTask(TaskContract):
    """
    Task contract for TTS synthesis.
    """

    name = "tts.synthesize"
    Payload = TTSSynthesizePayload
    Result = TTSSynthesizeResult

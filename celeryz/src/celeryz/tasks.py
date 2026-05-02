from .worker import app
from core.tasks.tts import TTSSynthesizeTask, TTSSynthesizeResult
from celery import Task


@app.task(name=TTSSynthesizeTask.name, bind=True)
def synthesize_audio(_: Task, payload: dict) -> dict:
    # Validate the payload using the Pydantic model defined in TTSSynthesizeTask
    # If the payload is invalid, a ValidationError will be raised and the task will
    # be marked as failed by Celery.
    p = TTSSynthesizeTask.Payload.model_validate(payload)
    return TTSSynthesizeResult(
        audio_url="http://example.com/audio.mp3", duration_seconds=3.5, job_id=p.job_id
    ).model_dump(mode="json")

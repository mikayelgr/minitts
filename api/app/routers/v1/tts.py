from fastapi import APIRouter, Depends, HTTPException
from http import HTTPStatus
from pydantic import BaseModel, Field, HttpUrl
from app.dependencies import get_celery_app, get_pg_session, AsyncSession, Celery
from core.db.models import User
from .dependencies import authenticate
from typing import Annotated
import core.db.queries.jobs
import core.db.queries.quotas
from core.db.models import Job, UsageEventType
import logging
from core.tasks import JobDefinition

router = APIRouter()
logger = logging.getLogger(__name__)


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


@router.post("/tts", status_code=HTTPStatus.ACCEPTED, response_model=Job)
async def submit(
    session: Annotated[AsyncSession, Depends(get_pg_session)],
    celery: Annotated[Celery, Depends(get_celery_app)],
    user: Annotated[User, Depends(authenticate)],
    payload: CreateTTSJobRequest,
):
    payload.text = payload.text.strip()
    required_tokens = len(payload.text.split(" "))
    # Check if the user has enough quota tokens to process the request. In our case we consider
    # a token to be equivalent to a single word, so we split the input text by spaces and count
    # the number of words to determine the token count.
    if user.quota_tokens_remaining - required_tokens < 0:
        raise HTTPException(
            status_code=HTTPStatus.PAYMENT_REQUIRED,
            detail="Quota exceeded. Please upgrade your plan.",
        )

    # Deduct quota tokens and persist the user record. We do this before enqueuing the job to ensure that
    # we don't accept more jobs than the user's quota allows.
    user.quota_tokens_remaining -= required_tokens
    await session.commit()

    """
    This endpoint is responsible for accepting TTS inference requests. It validates the input payload
    and enqueues a TTS job for asynchronous processing. Once the job is complete, the server will POST
    the result to the provided callback URL.
    """
    job = await core.db.queries.jobs.create_job(
        session,
        user,
        Job(
            text=payload.text,
            callback_url=payload.callback_url,
        ),
    )

    await core.db.queries.quotas.create_quota_usage_event(
        session,
        user,
        job,
        amount=required_tokens,
        event_type=UsageEventType.USAGE,
    )
    await session.commit()

    celery.send_task(JobDefinition.TTS_SYNTHESIZE, job_id=str(job.id))
    return job

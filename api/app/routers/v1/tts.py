from fastapi import APIRouter, Depends, HTTPException, Body
from http import HTTPStatus
from pydantic import BaseModel, Field, HttpUrl, field_validator
from app.dependencies import get_celery_app, get_pg_session, AsyncSession, Celery
from core.db.models import User
from .dependencies import authenticate
from typing import Annotated
import core.db.queries.jobs
import core.db.queries.quotas
import core.db.queries.users
from core.db.models import Job, UsageEventType
import ipaddress
import logging
from core.tasks import JobDefinition
import uuid

router = APIRouter()
logger = logging.getLogger(__name__)


class CreateTTSJobRequest(BaseModel):
    """CreateTTSJobRequest defines the expected payload for a TTS inference request."""

    text: str = Field(
        ...,
        title="TTS text to synthesize",
        description="The input text to be synthesized into speech.",
        example="Hello, world!",
        min_length=2,
        # max_length=1000,
    )

    callback_url: HttpUrl = Field(
        ...,
        title="Callback URL for job completion",
        description="The URL to which the server will POST the job result once inference is complete.",
        example="https://myapp.com/webhook",
    )

    @field_validator("callback_url")
    @classmethod
    def _reject_internal_callback_targets(cls, value: HttpUrl) -> HttpUrl:
        # Workers will issue an outbound POST to this URL. Block hosts that resolve literally to
        # loopback/private/link-local ranges so a client can't trick the worker into hitting
        # internal services (Postgres, Redis, cloud metadata at 169.254.169.254, etc.). Note: this
        # is a literal-IP / hostname-keyword check; it does not defeat DNS rebinding, which would
        # require validation at request time inside the worker as well.
        host = value.host
        if not host:
            raise ValueError("callback_url must include a host")

        if host.lower() in {"localhost", "ip6-localhost", "ip6-loopback"}:
            raise ValueError("callback_url must not point to a loopback host")

        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return value

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError("callback_url must not point to an internal/reserved IP range")
        return value


@router.post("/tts", status_code=HTTPStatus.ACCEPTED, response_model=Job)
async def submit(
    session: Annotated[AsyncSession, Depends(get_pg_session)],
    celery: Annotated[Celery, Depends(get_celery_app)],
    user: Annotated[User, Depends(authenticate)],
    payload: CreateTTSJobRequest = Body(..., description="The TTS inference request payload"),
):
    payload.text = payload.text.strip()
    required_tokens = len(payload.text.split(" "))

    # Re-fetch the user row with FOR UPDATE so the quota check + deduction is serialized against
    # concurrent requests from the same user. Without the lock, two requests can both observe the
    # pre-deduction balance and both succeed past the check, allowing overspend.
    locked_user = await core.db.queries.users.lock_user(session, user.id)
    if locked_user is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="User not found")

    if locked_user.quota_tokens_remaining < required_tokens:
        raise HTTPException(
            status_code=HTTPStatus.PAYMENT_REQUIRED,
            detail="Quota exceeded. Please upgrade your plan.",
        )

    locked_user.quota_tokens_remaining -= required_tokens

    job = await core.db.queries.jobs.create_job(
        session,
        locked_user,
        Job(
            text=payload.text,
            callback_url=str(payload.callback_url),
        ),
    )
    await session.flush()  # ensure job.id and quota_usage_event.id are assigned before enqueue

    quota_usage_event = await core.db.queries.quotas.create_quota_usage_event(
        session,
        locked_user,
        job,
        amount=required_tokens,
        event_type=UsageEventType.USAGE,
    )
    await session.flush()

    # Enqueue the Celery task before commit. If the broker is unreachable, the exception unwinds
    # the dependency's rollback path and the quota deduction / job row are discarded. Otherwise we
    # commit, releasing the user row lock and persisting both the deduction and the job record.
    try:
        celery.send_task(
            JobDefinition.TTS_SYNTHESIZE,
            (str(job.id), quota_usage_event.id),
            # Reuse the job UUID as the Celery task id so status lookups can correlate the two.
            task_id=str(job.id),
        )
    except Exception:
        logger.exception("Failed to enqueue TTS synthesize task for job=%s; rolling back", job.id)
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="Unable to enqueue job for processing. Please try again later.",
        )

    await session.commit()
    return job


class JobStatusResponse(BaseModel):
    status: str


@router.get("/{job_id}/status", status_code=HTTPStatus.OK, response_model=JobStatusResponse)
async def get_job_status_from_celery(
    job_id: str,
    celery: Annotated[Celery, Depends(get_celery_app)],
    session: Annotated[AsyncSession, Depends(get_pg_session)],
    user: Annotated[User, Depends(authenticate)],
):
    from celery.result import AsyncResult

    # Validate UUID format upfront
    try:
        uid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Job not found")

    # Look up the job in Postgres first to verify ownership. We use a non-locking read so this
    # endpoint can be polled without contending with the worker that holds the row lock during
    # processing — otherwise EXECUTING would be invisible to the client.
    job = await core.db.queries.jobs.get_job(session, uid)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Job not found")

    # Prefer the Celery result backend's view when it has one. Celery returns PENDING for unknown
    # task IDs as well as genuinely pending tasks, so PENDING means "fall back to the DB state".
    res = AsyncResult(job_id, app=celery)
    if res.state != "PENDING":
        return {"status": str(res.state).lower()}

    return {"status": job.state.value.lower()}


@router.get("/{job_id}/result", status_code=HTTPStatus.OK, response_model=Job)
async def get_job_result(
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_pg_session)],
    user: Annotated[User, Depends(authenticate)],
):
    try:
        uid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Job not found")

    # Verify ownership with a non-locking read first. Doing the lock attempt before the ownership
    # check would let unauthorized callers distinguish "exists and is currently being processed"
    # (423) from "doesn't exist" (404), which is an information leak.
    job = await core.db.queries.jobs.get_job(session, uid)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Job not found")

    result = await core.db.queries.jobs.get_job_safe(session, uid)
    if result.is_locked:
        raise HTTPException(status_code=HTTPStatus.LOCKED, detail="Job is currently locked and being processed")

    if not result.job:
        # Job was deleted between the ownership check and the locked read.
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Job not found")

    return result.job

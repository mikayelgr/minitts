from typing import cast
from unittest.mock import MagicMock

import pytest
from pydantic import HttpUrl
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session
from types_boto3_s3 import S3Client

from celeryz.util import GenerateAudioDeps, RetryableError, generate_and_store_audio
from core.db.models import JobState
from core.db.queries.jobs import JobAccessResult


# We define test dependencies once so we don't repeat them.
@pytest.fixture
def mock_deps() -> GenerateAudioDeps:
    """
    We return a GenerateAudioDeps object but use MagicMock() for the s3_client.
    This allows us to track if s3_client.put_object was called, without actually uploading to AWS.
    """
    mock_s3_client: S3Client = cast(S3Client, MagicMock())
    return GenerateAudioDeps(
        job_id="12345678-1234-5678-1234-567812345678",
        s3_client=mock_s3_client,
        s3_bucket="test-bucket",
        s3_public_endpoint=HttpUrl("http://public-s3.com"),
        tts_inference_endpoint="http://tts-api.com",
    )


def test_generate_and_store_audio_already_processed(mocker: MockerFixture, mock_deps: GenerateAudioDeps) -> None:
    mock_session: Session = cast(Session, MagicMock())

    # JobAccessResult with no job and is_locked=False means the row no longer matches the
    # CREATED/PENDING filter — i.e. it has already been processed. The task should silently no-op.
    mocker.patch("celeryz.util.lock_job_for_processing", return_value=JobAccessResult(job=None, is_locked=False))

    result = generate_and_store_audio(mock_session, mock_deps)
    assert result is None


def test_generate_and_store_audio_locked_retries(mocker: MockerFixture, mock_deps: GenerateAudioDeps) -> None:
    mock_session: Session = cast(Session, MagicMock())

    # is_locked=True means another transaction holds the row — the worker must surface this as a
    # retryable error rather than silently succeeding (which would lose the synthesis).
    mocker.patch("celeryz.util.lock_job_for_processing", return_value=JobAccessResult(job=None, is_locked=True))

    with pytest.raises(RetryableError, match="locked by another transaction"):
        generate_and_store_audio(mock_session, mock_deps)


def test_generate_and_store_audio_success(mocker: MockerFixture, mock_deps: GenerateAudioDeps) -> None:
    mock_session: Session = cast(Session, MagicMock())

    # 1. SETUP MOCK JOB
    mock_job: MagicMock = MagicMock()
    mock_job.id = "job-123"
    mock_job.user.username = "test_user"
    mocker.patch("celeryz.util.lock_job_for_processing", return_value=JobAccessResult(job=mock_job, is_locked=False))

    # 2. SETUP MOCK HTTP REQUEST
    mock_stream = mocker.patch("celeryz.util.httpx.stream")
    mock_context_manager = mock_stream.return_value.__enter__.return_value
    mock_context_manager.status_code = 200
    mock_context_manager.iter_bytes.return_value = [b"audio data"]

    # ACT
    result = generate_and_store_audio(mock_session, mock_deps)

    # ASSERT
    # Check that our code successfully modified the state to SUCCESS
    assert mock_job.state == JobState.SUCCESS
    assert result == mock_job

    # Check that the S3 mock recorded exactly one upload attempt
    mock_deps.s3_client.upload_fileobj.assert_called_once()
    mock_deps.s3_client.get_object_attributes.return_value = {"ObjectSize": 1000}

    # Check that the DB mock recorded a commit
    mock_session.commit.assert_called()


def test_generate_and_store_audio_http_failure_retryable(mocker: MockerFixture, mock_deps: GenerateAudioDeps) -> None:
    mock_session: Session = cast(Session, MagicMock())
    mock_job: MagicMock = MagicMock()
    mock_job.user.username = "test_user"
    mocker.patch("celeryz.util.lock_job_for_processing", return_value=JobAccessResult(job=mock_job, is_locked=False))

    # Fake an HTTP 500 Server Error. Under the indefinite-retry policy every non-200 from the
    # inference endpoint surfaces as RetryableError and the row is left in PENDING for the next
    # attempt; there is no in-util "max retries exhausted → FAILURE" branch anymore.
    mock_stream = mocker.patch("celeryz.util.httpx.stream")
    mock_context_manager = mock_stream.return_value.__enter__.return_value
    mock_context_manager.status_code = 500

    with pytest.raises(RetryableError, match="Non-200 response: 500"):
        generate_and_store_audio(mock_session, mock_deps)

    assert mock_job.state == JobState.PENDING


import httpx

def test_post_job_to_webhook_success(mocker: MockerFixture):
    mock_session = MagicMock()
    mock_job = MagicMock()
    mock_job.id = "job-123"
    mock_job.callback_url = "http://test-webhook.com"
    mock_job.webhook_attempts = 0
    mock_job.model_dump.return_value = {"id": "job-123"}
    
    mock_session.execute.return_value.scalar_one_or_none.return_value = mock_job
    
    mock_post = mocker.patch("celeryz.util.httpx.post")
    mock_post.return_value.raise_for_status.return_value = None
    
    from celeryz.util import post_job_to_webhook
    post_job_to_webhook(mock_session, "job-123")
    
    assert mock_job.webhook_attempts == 1
    assert mock_job.webhook_delivered_at is not None
    mock_post.assert_called_once_with("http://test-webhook.com", json={"id": "job-123"})
    

def test_post_job_to_webhook_http_error(mocker: MockerFixture):
    mock_session = MagicMock()
    mock_job = MagicMock()
    mock_job.callback_url = "http://test-webhook.com"
    mock_job.webhook_attempts = 0
    mock_session.execute.return_value.scalar_one_or_none.return_value = mock_job
    
    mock_post = mocker.patch("celeryz.util.httpx.post")
    mock_post.side_effect = httpx.RequestError("Network error")
    
    from celeryz.util import post_job_to_webhook
    with pytest.raises(RetryableError):
        post_job_to_webhook(mock_session, "job-123")
        
    assert mock_job.webhook_attempts == 1

def test_process_refund_success(mocker: MockerFixture):
    mock_session = MagicMock()
    
    mock_event = MagicMock()
    mock_event.user_id = "user-123"
    mock_event.amount = 100
    mock_event.job_id = "12345678-1234-5678-1234-567812345678"
    
    mock_user = MagicMock()
    mock_user.id = "user-123"
    mock_user.quota_tokens_remaining = 500
    
    # First call: original_event, Second call: existing_refund, Third call: user
    mock_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: mock_event),
        MagicMock(scalar_one_or_none=lambda: None),
        MagicMock(scalar_one=lambda: mock_user),
    ]
    
    from celeryz.util import process_refund
    process_refund(mock_session, "12345678-1234-5678-1234-567812345678", 1)
    
    assert mock_user.quota_tokens_remaining == 600
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()

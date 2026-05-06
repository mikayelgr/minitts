from typing import cast
from unittest.mock import MagicMock

import pytest
from pydantic import HttpUrl
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session
from types_boto3_s3 import S3Client

from celeryz.util import FatalError, GenerateAudioDeps, RetryableError, generate_audio
from core.db.models import JobState


# We define test dependencies once so we don't repeat them.
@pytest.fixture
def mock_deps() -> GenerateAudioDeps:
    """
    We return a GenerateAudioDeps object but use MagicMock() for the s3_client.
    This allows us to track if s3_client.put_object was called, without actually uploading to AWS.
    """
    mock_s3_client: S3Client = cast(S3Client, MagicMock())
    return GenerateAudioDeps(
        job_id="job-123",
        retries=0,  # Simulates that this is the first attempt
        max_retries=3,  # Will fail permanently after 3 tries
        s3_client=mock_s3_client,
        s3_bucket="test-bucket",
        s3_endpoint=HttpUrl("http://test-s3.com"),
        tts_inference_endpoint="http://tts-api.com",
    )


def test_generate_audio_already_processed(mocker: MockerFixture, mock_deps: GenerateAudioDeps) -> None:
    mock_session: Session = cast(Session, MagicMock())

    # 1. MOCKING RETURNS
    # Replace 'lock_job_for_processing' with a fake function that instantly returns None.
    # This simulates the situation where the database row is locked by another worker.
    mocker.patch("celeryz.util.lock_job_for_processing", return_value=None)

    # 2. ACT
    result = generate_audio(mock_session, mock_deps)

    # 3. ASSERT
    assert result is None


def test_generate_audio_success(mocker: MockerFixture, mock_deps: GenerateAudioDeps) -> None:
    mock_session: Session = cast(Session, MagicMock())

    # 1. SETUP MOCK JOB
    mock_job: MagicMock = MagicMock()
    mock_job.id = "job-123"
    mock_job.user.username = "test_user"
    mocker.patch("celeryz.util.lock_job_for_processing", return_value=mock_job)

    # 2. SETUP MOCK HTTP REQUEST
    mock_stream = mocker.patch("celeryz.util.httpx.stream")
    mock_context_manager = mock_stream.return_value.__enter__.return_value
    mock_context_manager.status_code = 200
    mock_context_manager.iter_bytes.return_value = [b"audio data"]

    # ACT
    result = generate_audio(mock_session, mock_deps)

    # ASSERT
    # Check that our code successfully modified the state to SUCCESS
    assert mock_job.state == JobState.SUCCESS
    assert result == mock_job

    # Check that the S3 mock recorded exactly one upload attempt
    mock_deps.s3_client.upload_fileobj.assert_called_once()
    mock_deps.s3_client.get_object_attributes.return_value = {"ObjectSize": 1000}

    # Check that the DB mock recorded a commit
    mock_session.commit.assert_called()


def test_generate_audio_http_failure_retryable(mocker: MockerFixture, mock_deps: GenerateAudioDeps) -> None:
    mock_session: Session = cast(Session, MagicMock())
    mock_job: MagicMock = MagicMock()
    mocker.patch("celeryz.util.lock_job_for_processing", return_value=mock_job)

    # Fake an HTTP 500 Server Error
    mock_stream = mocker.patch("celeryz.util.httpx.stream")
    mock_context_manager = mock_stream.return_value.__enter__.return_value
    mock_context_manager.status_code = 500

    # Check that our RetryableError is raised (since attempt 0 < max 3)
    with pytest.raises(RetryableError, match="Non-200 response: 500"):
        generate_audio(mock_session, mock_deps)

    assert mock_job.state == JobState.PENDING


def test_generate_audio_http_failure_fatal(mocker: MockerFixture, mock_deps: GenerateAudioDeps) -> None:
    # Simulating the scenario where we have exhausted all retries
    mock_deps.retries = 3

    mock_session: Session = cast(Session, MagicMock())
    mock_job: MagicMock = MagicMock()
    mocker.patch("celeryz.util.lock_job_for_processing", return_value=mock_job)

    # Fake an HTTP 500 Server Error
    mock_stream = mocker.patch("celeryz.util.httpx.stream")
    mock_context_manager = mock_stream.return_value.__enter__.return_value
    mock_context_manager.status_code = 500

    # Check that a FatalError is raised instead of a RetryableError
    with pytest.raises(FatalError, match="Max retries exhausted"):
        generate_audio(mock_session, mock_deps)

    assert mock_job.state == JobState.FAILURE

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
    mock_event.job_id = "job-123"
    
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
    process_refund(mock_session, "job-123", 1)
    
    assert mock_user.quota_tokens_remaining == 600
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()

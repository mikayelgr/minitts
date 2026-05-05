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
    # The real code does: pyreqwest_post(url).basic_auth(...).body_text(...).send()
    # Each time a mock is called, it returns a new mock. So we configure the final mock in the chain:
    mock_reqwest: MagicMock = mocker.patch("celeryz.util.pyreqwest_post")
    mock_post_chain: MagicMock = mock_reqwest.return_value.basic_auth.return_value.body_text.return_value
    mock_post_chain.send.return_value.status_code = 200  # Fake 200 OK
    mock_post_chain.send.return_value.body_reader = b"audio data"  # Fake Audio Bytes

    # ACT
    result = generate_audio(mock_session, mock_deps)

    # ASSERT
    # Check that our code successfully modified the state to SUCCESS
    assert mock_job.state == JobState.SUCCESS
    assert result == mock_job

    # Check that the S3 mock recorded exactly one upload attempt
    mock_deps.s3_client.put_object.assert_called_once()

    # Check that the DB mock recorded a commit
    mock_session.commit.assert_called()


def test_generate_audio_http_failure_retryable(mocker: MockerFixture, mock_deps: GenerateAudioDeps) -> None:
    mock_session: Session = cast(Session, MagicMock())
    mock_job: MagicMock = MagicMock()
    mocker.patch("celeryz.util.lock_job_for_processing", return_value=mock_job)

    # Fake an HTTP 500 Server Error
    mock_reqwest: MagicMock = mocker.patch("celeryz.util.pyreqwest_post")
    mock_reqwest.return_value.basic_auth.return_value.body_text.return_value.send.return_value.status_code = 500

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
    mock_reqwest: MagicMock = mocker.patch("celeryz.util.pyreqwest_post")
    mock_reqwest.return_value.basic_auth.return_value.body_text.return_value.send.return_value.status_code = 500

    # Check that a FatalError is raised instead of a RetryableError
    with pytest.raises(FatalError, match="Max retries exhausted"):
        generate_audio(mock_session, mock_deps)

    assert mock_job.state == JobState.FAILURE

from collections.abc import Generator, Iterator
from unittest.mock import MagicMock, patch

import pytest
import torch
from fastapi.testclient import TestClient
from httpx import Response

from endpoint import app, get_wav_header, SOPRANO_SAMPLE_RATE, SOPRANO_SAMPLE_WIDTH, SOPRANO_CHANNELS


# Mocking SopranoTTS to avoid loading the actual model during tests
@pytest.fixture(autouse=True)
def mock_soprano_model() -> Generator[MagicMock, None, None]:
    with patch("endpoint.SopranoTTS") as MockModel:
        mock_instance: MagicMock = MagicMock()
        MockModel.return_value = mock_instance

        # Mock infer_stream to yield a dummy tensor chunk
        def mock_infer_stream(text: str) -> Iterator[torch.Tensor]:
            yield torch.zeros(1)
            yield torch.ones(1)

        mock_instance.infer_stream.side_effect = mock_infer_stream
        yield mock_instance


def test_get_wav_header() -> None:
    header = get_wav_header(16000, 2, 1)
    assert isinstance(header, bytes)
    assert header.startswith(b"RIFF")
    assert b"WAVE" in header


def test_stream_speech_endpoint() -> None:
    with TestClient(app) as client:
        # TestClient with context manager triggers startup/shutdown lifespan events
        with client.stream(
            "POST",
            "/v1/audio/speech/stream",
            content="hello world",
            headers={"content-type": "text/plain"},
        ) as response:
            response: Response
            assert response.status_code == 200
            assert response.headers["content-type"] == "audio/wav"

            # Stream response check
            content = b""
            for chunk in response.iter_bytes():
                content += chunk

            assert len(content) > 0
            assert content.startswith(b"RIFF")

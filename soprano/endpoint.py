import asyncio
import warnings
import io
import wave
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from soprano import SopranoTTS
from contextlib import asynccontextmanager
import logging
from collections.abc import Iterable, Generator, AsyncIterable
from typing import Any
from torch import Tensor
from functools import lru_cache
import torch
import gc

# Silence a known PyTorch warning emitted inside soprano's ISTFT path.
warnings.filterwarnings(
    "ignore",
    message=r"An output with one or more elements was resized since it had shape \[\]",
    category=UserWarning,
    module=r"soprano\.vocos\.spectral_ops",
)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


# Fixed audio properties for Soprano-TTS output.
SOPRANO_SAMPLE_RATE = 32_000
SOPRANO_SAMPLE_WIDTH = 2  # 2 bytes for 16-bit audio
SOPRANO_CHANNELS = 1  # 1 for mono, 2 for stereo


@lru_cache
def get_wav_header(sample_rate: int, sample_width: int, channels: int) -> bytes:
    with io.BytesIO() as wav_file:
        with wave.open(wav_file, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(b"")
        return wav_file.getvalue()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Loading the SopranoTTS model into memory...")
    app.state.model = SopranoTTS(
        # intentionally setting the batch size to 1 to minimize latency for streaming responses
        # and make sure that in case this is scaled up to multiple instances, each instance can
        # handle requests independently without waiting for a batch to fill up
        decoder_batch_size=1,
    )

    logger.info("Model loaded. Warming up the model with sample data inferences...")
    warmup_data = [open(f"./warmup_data/{i+1}.txt", "r").read() for i in range(2)]
    for _ in range(2):
        warmup_tasks = [asyncio.to_thread(app.state.model.infer, data) for data in warmup_data]
        await asyncio.gather(*warmup_tasks)

    # freezing all the memory weights and caches after warmup to optimize for inference
    # performance and reduce memory fragmentation and latency spikes during actual requests
    gc.freeze()
    gc.collect()  # force a final GC pass to clean up any remaining unreferenced objects
    logger.info("Warmup complete. The model is ready to serve requests.")
    yield


class EndpointState:
    model: SopranoTTS


class EndpointApp(FastAPI):
    state: EndpointState


app = EndpointApp(lifespan=lifespan)


class AudioStreamingResponse(StreamingResponse):
    media_type = "audio/wav"


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/v1/audio/speech/stream", response_class=AudioStreamingResponse)
async def stream_speech(text: str = Query()) -> AsyncIterable[bytes]:
    """
    Stream the generated speech audio for the given text.
    """

    # Generate and yield the WAV header first.
    yield get_wav_header(
        SOPRANO_SAMPLE_RATE,
        SOPRANO_SAMPLE_WIDTH,
        SOPRANO_CHANNELS,
    )

    # Then, stream the raw audio chunks.
    generator: Generator[Tensor, Any] = app.state.model.infer_stream(text)

    # By offloading the synchronous, CPU-bound `next(generator)` call to a background
    # thread using `asyncio.to_thread`, we prevent the PyTorch inference from blocking
    # the main ASGI event loop, allowing the server to handle concurrent requests.
    #
    # Additionally, we're disabling PyTorch's autograd engine during inference. Since this service
    # only runs forward passes and never computes gradients, the computation graph that autograd
    # builds on every operation is pure overhead. inference_mode is stricter than no_grad, because
    # tensors created inside it cannot participate in autograd at all, letting PyTorch skip internal
    # bookkeeping that no_grad still performs.
    @torch.inference_mode()
    def _next_chunk():
        """Helper function to get the next audio chunk from the generator."""

        try:
            return next(generator)
        except StopIteration:
            return None

    while True:
        # Offload the blocking CPU-bound ML inference call to a background thread
        generated_chunk = await asyncio.to_thread(_next_chunk)
        if generated_chunk is None:
            break

        # Convert float32 [-1.0, 1.0] audio to 16-bit PCM integer [-32768, 32767].
        #
        # Formatting mismatch context:
        # The WAV header declares 16-bit PCM (integers), but SopranoTTS outputs
        # float32 values between -1.0 and 1.0. If raw float32 bytes are sent
        # directly, the audio player misinterprets the memory bits as extreme
        # integer fluctuations, resulting in a loud "screaming" white noise.
        #
        # The fix:
        # We multiply by 32767.0 (the max positive value of a 16-bit signed
        # integer) to scale the amplitude, then explicitly cast to torch.int16.
        # This aligns the model's data with the WAV header's format, enabling clean playback.
        # https://stackoverflow.com/questions/22895657/how-can-i-play-raw-samples-pcm-16-audio-data-record-from-android-in-web-using-w
        yield (generated_chunk * 32767.0).to(torch.int16).cpu().numpy().tobytes()

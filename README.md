# MiniTTS

MiniTTS is a production-minded foundation for an asynchronous Text-to-Speech service based on the [Soprano-1.1-80M](https://huggingface.co/ekwek/Soprano-1.1-80M) model.

For inference, the service runs the Soprano model on CPU, served behind [Granian](https://github.com/emmett-framework/granian) as the Rust-based inference server.

## What This Project Aims To Accomplish

The target system is an async TTS microservice where clients:

1. Submit text with a callback URL.
2. Receive a job identifier immediately.
3. Have synthesis processed in the background.
4. Receive completion via webhook. (as a stream of bytes as soon as the data is available)

In parallel, the platform should track quota usage (for example by character count or estimated audio seconds) so each request contributes to measurable, auditable usage.

This architecture is designed for reliability and scale: API traffic remains responsive while long-running synthesis jobs are handled by workers and queue infrastructure.

## How This Repository Intersects With The Task

Current codebase already provides the initial building blocks:

- FastAPI service scaffold in `api/app`.
- Health endpoint at `/health`.
- Environment-based configuration for Redis and Postgres.
- Docker Compose stack for Redis, RabbitMQ, Postgres, pgAdmin, RedisInsight, and the API container.
- Celery package scaffold (`celery/`) for async worker and task implementation.

This means the repository is already aligned with the requested stack direction (FastAPI + queue + database + Dockerized local development), and is ready for the remaining implementation work: job lifecycle endpoints, worker execution path, webhook delivery, and quota accounting logic.

## Quick Start

1. Ensure Docker is installed and runs locally.
2. From the project root, start the stack:

   ```bash
   docker compose up --build
   ```

3. Verify API health:

   ```bash
   curl http://localhost:8080/health
   ```

4. Stop all services:

   ```bash
   docker compose down
   ```

## Soprano Inference Service (CPU)

`soprano/` provides a dedicated inference microservice for the Soprano-1.1-80M model, exposing `/v1/audio/speech` and `/health` via a FastAPI + Granian stack. The API **streams audio chunks** in WAV format at 32kHz sample rate (which is the default for this model) to the client as they are generated, drastically reducing Time-To-First-Audio (TTFA).

### Production Limitations & Testing Needs

While functional, the streaming endpoint needs further refinement for production readiness. Here are the planned improvements to boost performance and robustness per endpoint:

- [ ] Handle mid-stream client disconnects to prevent memory leaks and zombie threads.
- [ ] Implement a mechanism to gracefully propagate errors that occur mid-stream.
- [ ] Add bounded concurrency limits and load shedding (429s) to prevent CPU thrashing.
- [ ] Optimize chunk buffer sizes to minimize Python garbage collection pauses during streaming.
- [ ] Track performance metrics like TTFA, RTF, and error rates via telemetry.
- [ ] Expand test coverage to include partial streams, disconnects, and heavy load testing.

<!-- Out of scope -->
<!-- - [ ] Integrate inference accelerations (ONNX/OpenVINO/quantization) to maximize CPU throughput. -->

### Latency-Focused Tooling And Optimizations

- Granian provides a low-latency, Rust-backed ASGI server for Python apps (benchmarks: <https://github.com/emmett-framework/granian/blob/master/benchmarks/vs.md>).
- `uvloop` is used as the event loop to reduce request overhead (benchmarks: <https://github.com/MagicStack/uvloop#performance>).
- Worker and thread counts are configurable via `WORKERS` and `THREADS` to tune concurrency.
- Optional model warm-up at startup (`WARMUP_ON_STARTUP=1`) runs an inference per worker on varied data out of `warmup_data/` to avoid first-request cold starts.

Run CPU (default):

```bash
cd soprano
docker compose up --build
```

Endpoints:

- CPU: `http://localhost:8081/health`

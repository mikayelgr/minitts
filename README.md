# MiniTTS

[![CI](https://github.com/mikayelgr/minitts/actions/workflows/ci.yml/badge.svg)](https://github.com/mikayelgr/minitts/actions/workflows/ci.yml)

MiniTTS is a production-minded foundation for an asynchronous Text-to-Speech service based on the [Soprano-1.1-80M](https://huggingface.co/ekwek/Soprano-1.1-80M) model. For inference, the service runs the Soprano model on CPU, served behind [Granian](https://github.com/emmett-framework/granian) as the Rust-based inference server.

## What This Project Aims To Accomplish

The target system is an async TTS microservice where clients:

1. Submit text with a callback URL.
2. Receive a job identifier immediately.
3. Have synthesis processed in the background.
4. Receive completion via webhook.

In parallel, the platform should track quota usage (for example by character count or estimated audio seconds) so each request contributes to measurable, auditable usage.

This architecture is designed for reliability and scale: API traffic remains responsive while long-running synthesis jobs are handled by workers and queue infrastructure.

## Architecture

The API accepts a TTS job, persists it to Postgres, and dispatches a Celery task through RabbitMQ. A worker consumes the task, calls the Soprano inference service, streams audio bytes back, updates the job row, stores the job result in Redis (Celery's result backend) and the inference result is stored in SeaweedFS as WAV audio file, and webhook post request is sent to the client's callback URL containing the audio URL of the generated file.

![MiniTTS architecture](docs/assets/minitts_architecture_v6.svg)

Producer (API) and consumer (worker) are intentionally decoupled through the broker, hence, the API can accept and queue work even when no worker is currently running, and worker restarts do not affect API availability.

## How This Repository Intersects With The Task

Current codebase already provides the initial building blocks:

- FastAPI service scaffold in `api/app`.
- Health endpoint at `GET /health` for all HTTP-exposed packages.
- TTS submission endpoint at `POST /v1/tts`.
- Environment-based configuration for Redis and Postgres.
- Docker Compose stack for Caddy, Redis, RedisInsight, RabbitMQ, SeaweedFS, Postgres, pgAdmin, the MiniTTS API container, the Celery worker container, the Soprano inference engine + API, as well as a small container which runs the intial Alembic migrations automatically on start.
- A developer-friendly landing page at `http://localhost:3000` that links to the main service subdomains.

Currently implemented HTTP surface includes:

- `GET /health` on the API.
- `POST /v1/tts` on the API for queued job submission.
- `GET /health` on the Soprano inference service
- `POST /v1/audio/speech/stream` on the Soprano inference service for audio generation returned as 32kHz mono WAV streams.

## Testing the End-to-End Workflow

You can test the full suite directly using the Swagger UI assuming that you've deployed the Docker Compose file which runs the whole suite:

1. Navigate to <http://api.localhost:3000/docs>.
2. Authorize using Basic Auth with the following sample credentials:
   - Username: `admin`
   - Password: `4`

> Note: No need for registration since for the sake of simplicity it's done automatically. You can test this out using other usernames as well coupled with `len(username)` as the password.

1. Use a service like [Webhook.site](https://webhook.site) to generate a unique callback URL.
2. Submit a TTS job via the `POST /v1/tts` endpoint using your Webhook.site URL as the `callback_url`.
3. You can then monitor the job state via the `/v1/tts/{job_id}/status` and `/v1/tts/{job_id}/result` endpoints, and eventually see the completion payload delivered to Webhook.site.

## Quick Start

1. Ensure Docker is installed and runs locally.
2. From the project root, build and run the full setup which configures MiniTTS end-to-end:

   ```bash
   docker compose up -d --build
   ```

3. If you need host ports during development, use the development-only compose overlay:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d redis rabbitmq postgres seaweedfs
   ```

   This command keeps the base stack unchanged and only publishes the ports for your local machine while you are developing.

   The overlay publishes:

   - Redis on `localhost:6379`
   - Postgres on `localhost:5432`
   - RabbitMQ AMQP on `localhost:5672`

   - SeaweedFS
      - Master UI on `localhost:9333`
      - Filer UI on `localhost:8888`
      - S3 Endpoint on `localhost:8333`

## Developer-friendly Gateway for All Services

> Note: This part assumes that you've run the full setup as indicated in the previous section.

1. Open the local gateway in your browser:

   ```text
   http://localhost:3000
   ```

   This serves a small index page that acts like a local control panel:

   - MiniTTS API: <http://api.localhost:3000>, the FastAPI app where request endpoints live and where TTS jobs will be accepted.
   - Soprano: <http://soprano-inference.localhost:3000>, the CPU inference API service that performs text-to-speech generation.
   - RedisInsight: <http://redisinsight.localhost:3000>, a Redis admin UI for inspecting cache/queue data and debugging queue state.
   - RabbitMQ: <http://rabbitmq.localhost:3000>, the broker UI for viewing message queues and worker traffic.
   - pgAdmin: <http://pgadmin.localhost:3000>, a database admin UI for browsing and managing Postgres.
   - SeaweedFS Master UI: <http://seaweedfs-master-ui.localhost:3000>, for inspecting the cluster and topology.
   - SeaweedFS Filer UI: <http://seaweedfs-filer-ui.localhost:3000>, for inspecting the stored audio files.

2. Verify API health:

   ```bash
   curl http://api.localhost:3000/health
   curl http://soprano-inference.localhost:3000/health
   ```

   The health of the remaining services is handled by Docker and the corresponding images.

3. Stop all services:

   ```bash
   docker compose down
   ```

## Running Services

The current Compose stack starts these services:

- `caddy`: local reverse proxy and landing page at `localhost:3000`.
- `api`: the FastAPI application that will accept TTS requests and expose HTTP endpoints.
- `celeryz`: the Celery worker that consumes queued jobs.
- `alembic-migrate`: the one-shot migration service that initializes the database schema.
- `soprano`: the CPU inference service that turns text into audio.
- `redis`: the Redis instance used for queueing and other fast shared state.
- `redisinsight`: a Redis UI for inspecting keys, queues, and runtime state.
- `rabbitmq`: the RabbitMQ broker used for message delivery between producers and workers.
- `postgres`: the Postgres database for persistent application data.
- `pgadmin`: a Postgres UI for inspecting tables and managing the database.
- `seaweedfs`: the SeaweedFS object storage system where generated audio files are persisted as WAVs.

For local development against the Dockerized infrastructure from the host machine, you need to configure these environment variables in the `.env` files of `celeryz/`, `core/`, and `api/` packages accordingly:

```text
CELERY_BROKER_URL=amqp://guest:guest@localhost:5672/
CELERY_RESULT_BACKEND_URL=redis://localhost:6379/0
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres

# Additional variables only for `celeryz/` package
TTS_INFERENCE_ENDPOINT=http://localhost:8081/v1/audio/speech/stream
## Assuming default SeaweedFS has been deployed from the provided Docker compose stack
AWS_ACCESS_KEY_ID=admin
AWS_SECRET_ACCESS_KEY=secret
S3_BUCKET=minitts
S3_ENDPOINT_URL=http://localhost:8333
S3_PUBLIC_ENDPOINT_URL=http://seaweedfs-s3.localhost:3000
```

## Soprano Inference Service (CPU)

`soprano/` provides a dedicated inference microservice for the Soprano-1.1-80M model, exposing `/v1/audio/speech/stream` and `/health` via a FastAPI + Granian stack. The API streams audio chunks in WAV format at 32kHz sample rate (which is the default for this model) to the client as they are generated, drastically reducing Time-To-First-Audio (TTFA).

### Latency-Focused Tooling And Optimizations

- Granian provides a low-latency, Rust-backed ASGI server for Python apps (benchmarks: <https://github.com/emmett-framework/granian/blob/master/benchmarks/vs.md>).
- `uvloop` is used as the event loop to reduce request overhead (benchmarks: <https://github.com/MagicStack/uvloop#performance>).

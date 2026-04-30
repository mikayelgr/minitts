# MiniTTS

MiniTTS is a production-minded foundation for an asynchronous Text-to-Speech service based on the [Soprano-1.1-80M](https://huggingface.co/ekwek/Soprano-1.1-80M) model.

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

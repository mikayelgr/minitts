FROM python:3.13-alpine
ENV PYTHONUNBUFFERED=1
# installing uv tooling which is necessary for this project
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Required runtime environment variables (provided by docker-compose / the deployer):
#   CELERY_BROKER_URL, CELERY_RESULT_BACKEND_URL, DATABASE_URL,
#   TTS_INFERENCE_ENDPOINT, S3_BUCKET, S3_ENDPOINT_URL, S3_PUBLIC_ENDPOINT_URL,
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /container
# Copy the entire repo structure so path dependencies resolve correctly. We assume that
# the Docker build context is the root of the project (where the main pyproject.toml is located).
COPY celeryz/ ./celeryz/
COPY core/ ./core/

WORKDIR /container/celeryz

# installing the dependencies globally so that they are available for the entire project
RUN uv sync --frozen --no-dev
CMD [ "sh", "-c", "celery -A celeryz.main:app worker --loglevel=warning" ]

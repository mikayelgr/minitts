FROM python:3.13-alpine
ENV PYTHONUNBUFFERED=1
# installing uv tooling which is necessary for this project
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ARG CELERY_BROKER_URL
ARG CELERY_RESULT_BACKEND_URL
ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /container
# Copy the entire repo structure so path dependencies resolve correctly. We assume that
# the Docker build context is the root of the project (where the main pyproject.toml is located).
COPY celeryz/ ./celeryz/
COPY core/ ./core/

WORKDIR /container/celeryz

# installing the dependencies globally so that they are available for the entire project
RUN uv sync --frozen --no-dev
CMD [ "sh", "-c", "celery -A celeryz.worker:app worker --loglevel=info" ]

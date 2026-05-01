FROM python:3.13-alpine
# installing uv tooling which is necessary for this project
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /celery

COPY pyproject.toml .
# installing the dependencies globally so that they are available for the entire project
RUN uv pip install --system -r pyproject.toml

# https://stackoverflow.com/a/59812588/14575901
ENV PYTHONUNBUFFERED=1

ARG CELERY_BROKER_URL
ARG CELERY_RESULT_BACKEND

COPY . .
CMD [ "sh", "-c", "celery -A worker.celery_app worker --loglevel=info" ]

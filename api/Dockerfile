FROM python:3.13-alpine
# https://stackoverflow.com/a/59812588/14575901
ENV PYTHONUNBUFFERED=1
# installing uv tooling which is necessary for this project
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Required runtime environment variables (provided by docker-compose / the deployer):
#   CELERY_BROKER_URL, CELERY_RESULT_BACKEND_URL, DATABASE_URL
ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /container
COPY api/ ./api/
COPY core/ ./core/

WORKDIR /container/api
# installing the dependencies globally so that they are available for the entire project
RUN uv sync --frozen --no-dev
EXPOSE 8080

CMD [ "sh", "-c", "uvicorn app.main:app --port 8080 --host 0.0.0.0 --no-access-log" ]

FROM python:3.13-alpine
# https://stackoverflow.com/a/59812588/14575901
ENV PYTHONUNBUFFERED=1
# installing uv tooling which is necessary for this project
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /api

# these are the environment variables that will be used by the application, they will be passed in at runtime
# these are strictly necessary for the application to run, it's the user's responsibility to provide them when
# running the container.
ARG CELERY_BROKER_URL
ARG CELERY_RESULT_BACKEND_URL
ARG DATABASE_URL
ENV UV_PROJECT_ENVIRONMENT=/usr/local

COPY . .
# installing the dependencies globally so that they are available for the entire project
RUN uv sync --frozen --no-dev

EXPOSE 8080

CMD [ "sh", "-c", "fastapi run app/main.py --port 8080 --host 0.0.0.0" ]

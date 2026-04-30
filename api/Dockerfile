FROM python:3.13-alpine
# installing uv tooling which is necessary for this project
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /api

COPY pyproject.toml .
# installing the dependencies globally so that they are available for the entire project
RUN uv pip install --system -r pyproject.toml

ENV PORT=8080

# these are the environment variables that will be used by the application, they will be passed in at runtime
# these are strictly necessary for the application to run, it's the user's responsibility to provide them when
# running the container.
ARG REDIS_URL
ARG POSTGRES_URL

COPY . .
CMD [ "sh", "-c", "fastapi run app/main.py --port ${PORT} --host 0.0.0.0" ]

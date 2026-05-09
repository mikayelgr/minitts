FROM python:3.13-alpine
ENV PYTHONUNBUFFERED=1
# installing uv tooling which is necessary for this project
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Required runtime environment variable (provided by docker-compose / the deployer):
#   DATABASE_URL
ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /container
COPY core /container/

# Install all core and extra dependencies which are necessary for running the migrations
# using alembic.
RUN uv sync --frozen --no-dev --extra=migration

CMD [ "alembic", "upgrade", "head" ]
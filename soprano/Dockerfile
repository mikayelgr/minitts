# since pytorch doesn't support alpine, we can use at most the slim version
# of the image in order to minimize the image size while still being able
# to install the necessary dependencies
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /soprano

ENV HF_HUB_DISABLE_PROGRESS_BARS=1
ENV UV_PROJECT_ENVIRONMENT=/usr/local

COPY . .
RUN uv sync --frozen --no-dev
# installing just
RUN curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /soprano
# Pre-downloading the model weights to not waste startup time during runtime.
RUN /soprano/just preload

EXPOSE 8081
CMD [ "/soprano/just", "start" ]

# since pytorch doesn't support alpine, we can use at most the slim version
# of the image in order to minimize the image size while still being able
# to install the necessary dependencies
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV HF_HUB_DISABLE_PROGRESS_BARS=1
ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /soprano

COPY . .
RUN uv sync --frozen --no-dev
# Cleaning up apt lists cache to minimize image size. This is especially important since the image
RUN apt update -y && apt install build-essential -y && apt clean -y && rm -rf /var/lib/apt/lists/*
# Pre-downloading the model weights to not waste startup time during runtime.
RUN make preload

EXPOSE 8081
# Running soprano using Granian with uvloop for higher throughput.
CMD [ "make", "start" ]

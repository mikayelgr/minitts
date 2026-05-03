#!/bin/bash

docker compose run -dp 5672:5672 rabbitmq
docker compose run -dp 5432:5432 postgres
docker compose run -dp 6379:6379 redis

# Core services
docker compose run --build -dp 8080:8080 api
docker compose run --build -dp 8081:8081 soprano

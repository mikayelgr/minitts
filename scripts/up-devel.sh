#!/bin/bash

docker compose run -dp 5672:5672 rabbitmq
docker compose run -dp 5432:5432 postgres
docker compose run -dp 6379:6379 redis

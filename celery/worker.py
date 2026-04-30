import os
from celery import Celery

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672/")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://default@redis:6379/0")

app = Celery("minitts_worker", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)
app.conf.update(
    task_compression="gzip",
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-acks-late
    task_acks_late=True,
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-reject-on-worker-lost
    task_reject_on_worker_lost=True,
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-create-missing-queues
    task_create_missing_queues=True,
)

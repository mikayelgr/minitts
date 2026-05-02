from .worker import app
from core.tasks import Task
from celery import Task as CeleryTask


@app.task(name=Task.TTS_SYNTHESIZE, bind=True)
def synthesize_audio(self: CeleryTask):
    pass

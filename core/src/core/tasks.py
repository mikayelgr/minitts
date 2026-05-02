from enum import StrEnum


class QueueTask(StrEnum):
    """
    Enum for defining task names used in the Celery worker.
    """

    TTS_SYNTHESIZE = "tts.synthesize"

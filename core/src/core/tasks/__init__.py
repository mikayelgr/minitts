from . import *
from enum import StrEnum


class JobState(StrEnum):
    """
    Enum representing the state of a job.
    """

    CREATED = "created"
    PENDING = "pending"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILURE = "failure"


class JobDefinition(StrEnum):
    TTS_SYNTHESIZE = "tts.synthesize"
    TTS_REFUND = "tts.refund"

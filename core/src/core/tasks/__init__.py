from pydantic import BaseModel
from enum import StrEnum
from typing import ClassVar


class TaskState(StrEnum):
    """
    Enum representing the state of a task.
    """

    CREATED = "created"
    PENDING = "pending"
    SUCCESS = "success"
    FAILURE = "failure"


class TaskContract:
    """
    Base model for a task, containing common fields.
    """

    name: ClassVar[str]
    Payload: type[BaseModel]
    Result: type[BaseModel]

from datetime import datetime
import uuid

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import func, CheckConstraint, Column, DateTime, Enum
from core.tasks import TaskState


class User(SQLModel, table=True):
    """
    Represents a user in the system with authentication and quota information.
    """

    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    username: str = Field(nullable=False, unique=True, max_length=50)
    quota_tokens_remaining: int = Field(default=100_000, nullable=False)
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))

    # Relationships
    quota_events: list["QuotaUsageEvent"] = Relationship(back_populates="user")


class QuotaUsageEvent(SQLModel, table=True):
    """
    Represents an event where a user consumes quota tokens, associated with a job.
    """

    __tablename__ = "quota_usage_events"

    id: int | None = Field(default=None, primary_key=True)
    amount: int = Field(nullable=False, gt=0)  # Ensure amount is positive
    quota_type: str = Field(nullable=False, max_length=50)
    job_id: uuid.UUID = Field(foreign_key="jobs.id", nullable=False)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)

    # Table-level constraints & indexes
    __table_args__ = (CheckConstraint("amount > 0", name="check_positive_amount"),)

    # Relationships
    user: "User" = Relationship(back_populates="quota_events")
    job: "Job" = Relationship(back_populates="associated_quota_usage_events")


class Job(SQLModel, table=True):
    """
    Represents a job in the system, which can have an associated state and creation timestamp.
    """

    __tablename__ = "jobs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    state: TaskState = Field(sa_column=Column(Enum(TaskState), nullable=False, default=TaskState.CREATED))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))

    associated_quota_usage_events: list["QuotaUsageEvent"] = Relationship(back_populates="job")

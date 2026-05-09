from datetime import datetime
import uuid

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import func, CheckConstraint, Column, DateTime, Enum
from core.tasks import JobState
from enum import StrEnum


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
    jobs: list["Job"] = Relationship(back_populates="user", cascade_delete=True)
    quota_events: list["QuotaUsageEvent"] = Relationship(back_populates="user", cascade_delete=True)


class UsageEventType(StrEnum):
    USAGE = "USAGE"
    REFUND = "REFUND"


class QuotaUsageEvent(SQLModel, table=True):
    """
    Represents an event where a user consumes quota tokens, associated with a job.
    """

    __tablename__ = "quota_usage_events"

    id: int | None = Field(default=None, primary_key=True)
    amount: int = Field(nullable=False, gt=0)  # Ensure amount is positive
    event_type: UsageEventType = Field(
        sa_column=Column(Enum(UsageEventType), nullable=False, name="usage_event_type"),
    )
    job_id: uuid.UUID = Field(foreign_key="jobs.id", nullable=False, ondelete="CASCADE")
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, ondelete="CASCADE")

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
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, ondelete="CASCADE")
    state: JobState = Field(
        sa_column=Column(Enum(JobState), nullable=False, default=JobState.CREATED, name="task_state"),
    )
    text: str = Field(nullable=False, min_length=2)
    # Most modern browsers support URLs up to around 2000 characters, so we set 2048
    # as the max length for callback URLs.
    callback_url: str = Field(nullable=False, max_length=2048)
    audio_url: str | None = Field(default=None, max_length=2048)
    duration_seconds: float | None = Field(default=None, gt=0)
    error: str | None = Field(default=None)

    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    webhook_delivered_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    webhook_attempts: int = Field(default=0, nullable=False, ge=0)

    # Relationships
    user: "User" = Relationship(back_populates="jobs")
    associated_quota_usage_events: list["QuotaUsageEvent"] = Relationship(back_populates="job", cascade_delete=True)

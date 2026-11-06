"""Pydantic models for every piece of data that crosses a boundary."""
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# Ids are short slugs; restricting them keeps tool arguments from the LLM predictable.
RecordId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- Domain data (fixtures) ----

class CandidateStage(StrEnum):
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"


class Candidate(_Model):
    id: RecordId
    name: str = Field(min_length=1)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    job_id: RecordId
    stage: CandidateStage


class Job(_Model):
    id: RecordId
    title: str = Field(min_length=1)
    team: str = Field(min_length=1)
    location: str = Field(min_length=1)


class InterviewStatus(StrEnum):
    NOT_SCHEDULED = "not_scheduled"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    PENDING_FEEDBACK = "pending_feedback"


class Interview(_Model):
    candidate_id: RecordId
    status: InterviewStatus
    scheduled_at: datetime | None = None
    interviewer: str | None = None

    @model_validator(mode="after")
    def _scheduled_needs_a_time(self) -> "Interview":
        if self.status == InterviewStatus.SCHEDULED and self.scheduled_at is None:
            raise ValueError("a scheduled interview needs scheduled_at")
        return self


class Message(_Model):
    sender: Literal["candidate", "recruiter"]
    text: str = Field(min_length=1)
    sent_at: datetime


class Conversation(_Model):
    id: RecordId
    candidate_id: RecordId
    messages: list[Message] = Field(min_length=1)


# ---- Tool inputs ----

class GetCandidateInput(_Model):
    candidate_id: RecordId


class GetInterviewStatusInput(_Model):
    candidate_id: RecordId


class GetJobInput(_Model):
    job_id: RecordId


# Tool outputs are the domain models above (Candidate, Interview, Job).


# ---- Run state (SQLite) ----

class RunStatus(StrEnum):
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class StepType(StrEnum):
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    LLM_MESSAGE = "llm_message"
    ERROR = "error"


class AgentStep(_Model):
    index: int = Field(ge=0)
    type: StepType
    name: str | None = None
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int = Field(default=0, ge=0)
    ts: datetime


class AgentRun(_Model):
    id: str
    conversation_id: RecordId
    status: RunStatus
    instructions: str | None = None
    steps: list[AgentStep] = Field(default_factory=list)
    draft_text: str | None = None
    final_text: str | None = None
    rejection_reason: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

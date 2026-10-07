"""Request and response shapes. Everything crossing the API boundary is declared here."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Kind = Literal["central", "branch", "bookmobile", "research"]
TicketCategory = Literal["billing", "access", "data", "outage", "general"]
TicketPriority = Literal["high", "normal", "low"]
TicketTeam = Literal["finance-ops", "identity", "data-platform", "platform-sre", "triage"]
TicketStatus = Literal["awaiting_review", "accepted", "changed"]


class Library(BaseModel):
    """One facility. This is the record type the whole app is built around."""

    id: int
    name: str
    city: str
    state: str = Field(min_length=2, max_length=2)
    kind: Kind
    year_founded: int
    annual_visits: int
    has_makerspace: bool


class LibraryCreate(BaseModel):
    """The write path. Note that ``id`` is assigned by the server, never by the caller."""

    name: str = Field(min_length=1, max_length=120)
    city: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=2, max_length=2)
    kind: Kind
    year_founded: int = Field(ge=1700, le=2100)
    annual_visits: int = Field(ge=0)
    has_makerspace: bool = False


class Page(BaseModel):
    """Every list endpoint returns this shape. Copy it for new list endpoints."""

    items: list[Library]
    total: int
    limit: int
    offset: int


class ModelPayload(BaseModel):
    """How a model-backed endpoint reports what the model said.

    Every model-backed response embeds this, so a caller can always see the
    confidence and which model version produced the answer.
    """

    value: object
    confidence: float
    model_version: str
    latency_ms: int


class DescribeResponse(BaseModel):
    library_id: int
    description: str
    model: ModelPayload


class ErrorBody(BaseModel):
    """The one error shape. Every 4xx and 5xx this app raises looks like this."""

    detail: str
    code: str


class TicketCreate(BaseModel):
    """A ticket submitted for model-assisted triage."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=1000)
    body: str = Field(min_length=1, max_length=1000)

    @field_validator("subject", "body")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("ticket text must not be empty")
        return value


class TicketRecommendation(BaseModel):
    """The original model recommendation and the values available to a human."""

    category: TicketCategory
    priority: TicketPriority
    team: TicketTeam
    draft_reply: str = Field(min_length=1, max_length=1000)


class Ticket(BaseModel):
    """A queued ticket with its current human-review state."""

    id: str
    category: TicketCategory
    priority: TicketPriority
    team: TicketTeam
    confidence: float = Field(ge=0.0, le=1.0)
    model_version: str = Field(min_length=1)
    status: TicketStatus
    draft_reply: str = Field(min_length=1, max_length=1000)
    reply_sent: bool
    suggested: TicketRecommendation


class TicketReview(BaseModel):
    """A human decision to accept or replace a queued recommendation."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["accept", "change"]
    category: Optional[TicketCategory] = None
    priority: Optional[TicketPriority] = None
    team: Optional[TicketTeam] = None
    draft_reply: Optional[str] = Field(default=None, min_length=1, max_length=1000)


class SummaryResponse(BaseModel):
    """`GET /libraries/summary` — see specs/filtered-summary.md §5."""

    count: int
    filters: dict
    summary: Optional[str]
    word_count: int
    truncated: bool
    cached: bool
    model: Optional[ModelPayload]
    model_error: Optional[str]

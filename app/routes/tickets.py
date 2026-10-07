"""Support ticket triage and human-review queue endpoints."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.model_client import ModelTimeout, ModelUnavailable, get_client
from app.models import (
    Ticket,
    TicketCreate,
    TicketRecommendation,
    TicketReview,
    TicketStatus,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])

# Queue records are intentionally process-local: the specification excludes durable
# persistence and ownership across service restarts.
_queue: dict[str, Ticket] = {}


def _recommendation(value: dict) -> TicketRecommendation:
    return TicketRecommendation(
        category=value["category"],
        priority=value["priority"],
        team=value["team"],
        draft_reply=value["draft_reply"],
    )


def _queue_item(
    ticket_id: str,
    recommendation: TicketRecommendation,
    confidence: float,
    model_version: str,
    status: TicketStatus = "awaiting_review",
) -> Ticket:
    return Ticket(
        id=ticket_id,
        category=recommendation.category,
        priority=recommendation.priority,
        team=recommendation.team,
        confidence=confidence,
        model_version=model_version,
        status=status,
        draft_reply=recommendation.draft_reply,
        reply_sent=False,
        suggested=recommendation,
    )


@router.post("/triage", response_model=Ticket, status_code=201)
def triage_ticket(body: TicketCreate) -> Ticket:
    """Classify a ticket, queue its recommendation, and return the current item."""
    try:
        result = get_client().complete(
            "classify_ticket",
            {"subject": body.subject, "body": body.body},
        )
    except ModelTimeout as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    recommendation = _recommendation(result.value)
    ticket_id = f"ticket-{uuid4().hex}"
    ticket = _queue_item(
        ticket_id,
        recommendation,
        result.confidence,
        result.model_version,
    )
    _queue[ticket_id] = ticket
    return ticket


@router.get("/{ticket_id}", response_model=Ticket)
def get_ticket(ticket_id: str) -> Ticket:
    """Return the current queue status and complete recommendation."""
    ticket = _queue.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"unknown ticket id {ticket_id}")
    return ticket


@router.post("/{ticket_id}/review", response_model=Ticket)
def review_ticket(ticket_id: str, body: TicketReview) -> Ticket:
    """Accept the recommendation or replace its human-review values."""
    ticket = _queue.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"unknown ticket id {ticket_id}")

    if body.action == "accept":
        ticket = _queue_item(
            ticket_id,
            ticket.suggested,
            ticket.confidence,
            ticket.model_version,
            status="accepted",
        )
        ticket.suggested = ticket.suggested
        _queue[ticket_id] = ticket
        return ticket

    if body.action != "change":
        raise HTTPException(status_code=422, detail="review action must be 'accept' or 'change'")

    replacement = TicketRecommendation(
        category=body.category or ticket.suggested.category,
        priority=body.priority or ticket.suggested.priority,
        team=body.team or ticket.suggested.team,
        draft_reply=body.draft_reply or ticket.suggested.draft_reply,
    )
    ticket = Ticket(
        id=ticket.id,
        category=replacement.category,
        priority=replacement.priority,
        team=replacement.team,
        confidence=ticket.confidence,
        model_version=ticket.model_version,
        status="changed",
        draft_reply=replacement.draft_reply,
        reply_sent=False,
        suggested=ticket.suggested,
    )
    _queue[ticket_id] = ticket
    return ticket

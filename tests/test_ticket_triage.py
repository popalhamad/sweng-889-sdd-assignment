"""Acceptance tests for the Support Ticket Triage specification."""

from __future__ import annotations

import pytest

from app import model_client as mc


TICKET = {
    "subject": "Refund for duplicate charge",
    "body": "I was billed twice for my September membership. Please refund one.",
}


def test_ac1_classifies_and_queues_ticket(client):
    response = client.post("/tickets/triage", json=TICKET)

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["category"] in {"billing", "access", "data", "outage", "general"}
    assert body["priority"] in {"high", "normal", "low"}
    assert body["team"]
    assert 0.0 <= body["confidence"] <= 1.0
    assert body["model_version"] in {"v1", "v2"}
    assert body["status"] == "awaiting_review"
    assert body["draft_reply"]
    assert body["reply_sent"] is False


def test_ac2_routes_recognized_categories_to_expected_teams(client):
    cases = [
        ("Refund for duplicate charge", "billing", "finance-ops"),
        ("Cannot login", "access", "identity"),
        ("CSV import failed", "data", "data-platform"),
        ("Site is down", "outage", "platform-sre"),
    ]

    for subject, category, team in cases:
        body_text = (
            "My password stopped working and I am locked out."
            if category == "access"
            else "Please help with this request."
        )
        response = client.post(
            "/tickets/triage",
            json={"subject": subject, "body": body_text},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["category"] == category
        assert body["team"] == team


def test_ac3_sets_high_priority_for_urgent_language(client):
    response = client.post(
        "/tickets/triage",
        json={
            "subject": "URGENT: blocked account",
            "body": "The service is down and I need access immediately.",
        },
    )

    assert response.status_code == 201
    assert response.json()["priority"] == "high"


def test_ac4_handles_general_tickets_without_guessing(client):
    response = client.post(
        "/tickets/triage",
        json={"subject": "Help", "body": "Please call me."},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["category"] == "general"
    assert body["team"] == "triage"
    assert body["status"] == "awaiting_review"


def test_ac5_preserves_low_confidence_for_human_review(client, monkeypatch):
    monkeypatch.setenv("STUB_WRONGNESS", "1.0")
    mc.reset_client()

    response = client.post("/tickets/triage", json=TICKET)

    assert response.status_code == 201
    body = response.json()
    assert body["confidence"] < 0.50
    assert body["status"] == "awaiting_review"
    assert body["reply_sent"] is False


def test_ac6_human_accept_keeps_suggestion(client):
    queued = client.post("/tickets/triage", json=TICKET)
    ticket_id = queued.json()["id"]

    response = client.post(
        f"/tickets/{ticket_id}/review",
        json={"action": "accept"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["category"] == body["suggested"]["category"]
    assert body["priority"] == body["suggested"]["priority"]
    assert body["team"] == body["suggested"]["team"]
    assert body["draft_reply"] == body["suggested"]["draft_reply"]
    assert body["reply_sent"] is False


def test_ac7_human_change_overrides_suggestion(client):
    queued = client.post("/tickets/triage", json=TICKET)
    ticket_id = queued.json()["id"]

    response = client.post(
        f"/tickets/{ticket_id}/review",
        json={
            "action": "change",
            "category": "general",
            "priority": "high",
            "team": "triage",
            "draft_reply": "We need a human to investigate this request.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "changed"
    assert body["category"] == "general"
    assert body["priority"] == "high"
    assert body["team"] == "triage"
    assert body["draft_reply"] == "We need a human to investigate this request."
    assert body["suggested"]["category"] != "general" or body["suggested"]["priority"] != "high"


def test_ac8_keeps_near_duplicates_separate(client):
    first = client.post(
        "/tickets/triage",
        json={
            "subject": "Charged twice",
            "body": "My card was charged two times for the same membership renewal.",
        },
    )
    second = client.post(
        "/tickets/triage",
        json={
            "subject": "Charged twice for my renewal",
            "body": "The card was charged twice for the same renewal.",
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert client.get(f"/tickets/{first.json()['id']}").json()["status"] == "awaiting_review"
    assert client.get(f"/tickets/{second.json()['id']}").json()["status"] == "awaiting_review"


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"subject": 123, "body": "A body"},
        {"subject": "A subject", "body": 123},
        {"subject": "A" * 1001, "body": "A body"},
        {"subject": "A subject", "body": "B" * 1001},
    ],
)
def test_ac9_rejects_malformed_request_shapes(client, payload):
    response = client.post("/tickets/triage", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["detail"]
    assert body["code"]


@pytest.mark.parametrize(
    "payload",
    [
        {"subject": "", "body": "Body with no subject"},
        {"subject": "Subject with no body", "body": "   "},
        {"subject": "", "body": ""},
    ],
)
def test_ac10_rejects_missing_ticket_text(client, payload):
    response = client.post("/tickets/triage", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["detail"]
    assert body["code"]


def test_ac11_returns_503_when_model_is_unavailable(client, monkeypatch):
    monkeypatch.setenv("STUB_FAILURE_RATE", "1.0")
    mc.reset_client()

    response = client.post("/tickets/triage", json=TICKET)

    assert response.status_code == 503
    assert response.json()["code"] == "model_unavailable"


def test_ac12_returns_504_when_model_times_out(client, monkeypatch):
    monkeypatch.setenv("STUB_LATENCY_MS", "900")
    monkeypatch.setenv("STUB_TIMEOUT_MS", "100")
    monkeypatch.setenv("STUB_SLEEP", "0")
    mc.reset_client()

    response = client.post("/tickets/triage", json=TICKET)

    assert response.status_code == 504
    assert response.json()["code"] == "model_timeout"


def test_ac13_returns_current_queue_state(client):
    queued = client.post("/tickets/triage", json=TICKET)
    ticket_id = queued.json()["id"]

    response = client.get(f"/tickets/{ticket_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == ticket_id
    assert body["status"] == "awaiting_review"
    assert body["confidence"] >= 0.0
    assert body["model_version"]


def test_ac14_rejects_invalid_review_actions(client):
    queued = client.post("/tickets/triage", json=TICKET)
    ticket_id = queued.json()["id"]

    response = client.post(
        f"/tickets/{ticket_id}/review",
        json={"action": "unknown"},
    )

    assert response.status_code == 422
    assert client.get(f"/tickets/{ticket_id}").json()["status"] == "awaiting_review"


def test_ac15_keeps_accepted_or_changed_status_visible(client):
    queued = client.post("/tickets/triage", json=TICKET)
    ticket_id = queued.json()["id"]

    accepted = client.post(
        f"/tickets/{ticket_id}/review",
        json={"action": "accept"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"

    changed = client.post(
        f"/tickets/{ticket_id}/review",
        json={"action": "change", "priority": "low"},
    )
    assert changed.status_code == 200
    assert changed.json()["status"] == "changed"
    assert changed.json()["priority"] == "low"

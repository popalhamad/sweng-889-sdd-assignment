# Feature Specification — Support Ticket Triage

**Status:** draft  
**Author:** specification author  
**Reviewers:** —  
**Date:** 2026-10-06

---

## 1. Intent

The Support Ticket Triage feature turns an incoming support request into a structured
recommendation and places it in a human-review queue. A human can accept the suggested
category, priority, team, and draft reply or replace those values before the ticket is
handled further. This feature is an aid to triage, not an autonomous responder.

## 2. User stories

- As a support agent, I want the incoming ticket to be assigned a category, priority,
  team, and draft reply so that I can begin work with a consistent starting point.
- As a support agent, I want low-confidence recommendations to remain visible and queued
  for review so that uncertain predictions are not treated as facts.
- As a support agent, I want to accept or replace the model's recommendation so that the
  queue reflects a human decision.
- As a support operator, I want every queued ticket to expose its current status so that
  accepted, changed, and awaiting-review items are distinguishable.
- As a support operator, I want malformed or incomplete tickets to be rejected with a
  validation error rather than being routed with guessed information.

## 3. Acceptance criteria

1. Given a valid ticket with non-empty subject and body, when `POST /tickets/triage` is
   called, then the response is HTTP 201 and contains a ticket identifier, category,
   priority, suggested team, confidence, model version, `awaiting_review` status, a
   non-empty draft reply, and `reply_sent: false`.
2. Given a ticket that the model classifies as `billing`, `access`, `data`, or `outage`,
   when it is triaged, then the response exposes the corresponding category and the
   repository-defined team (`finance-ops`, `identity`, `data-platform`, or
   `platform-sre`) with the model's confidence and version.
3. Given an urgent ticket containing language such as "urgent", "asap", "immediately",
   "blocked", or "down", when it is triaged, then the response reports priority `high`.
4. Given a ticket with no recognized category or keyword signal, when it is triaged,
   then the response reports category `general`, team `triage`, and priority `normal` or
   `low` according to the model result.
5. Given a model result with confidence below `0.50`, when the ticket is triaged, then
   the response preserves that score, marks the item `awaiting_review`, and does not send
   the draft reply automatically.
6. Given a ticket that has been queued, when a human calls
   `POST /tickets/{ticket_id}/review` with `action: accept`, then the queue status is
   `accepted`, the suggested values are retained, and `reply_sent` remains `false` unless
   a separate explicit send operation is added.
7. Given a ticket that has been queued, when a human calls
   `POST /tickets/{ticket_id}/review` with `action: change` and replacement values for
   category, priority, team, and/or draft reply, then the queue status is `changed`, the
   replacement values are returned, and the model predictions remain available as the
   original suggested values.
8. Given two separately submitted near-duplicate tickets, when both are triaged, then
   each receives a distinct ticket identifier and remains in the queue; the feature does
   not auto-merge, auto-close, or suppress either item.
9. Given a request whose JSON body is not an object, whose `subject` or `body` is not a
   string, or whose values exceed the stated field limits, when the request is submitted,
   then the response is HTTP 422 and contains the repository's `ErrorBody` shape.
10. Given a ticket with an empty subject or an empty body, when the ticket is submitted,
    then the response is HTTP 422 and no queue item is created.
11. Given a valid ticket and a model that raises `ModelUnavailable`, when triage is
    attempted, then the response is HTTP 503 with `ErrorBody`, and no item is queued.
12. Given a valid ticket and a model that raises `ModelTimeout`, when triage is attempted,
    then the response is HTTP 504 with `ErrorBody`, and no item is queued.
13. Given a queued ticket, when its current state is requested with
    `GET /tickets/{ticket_id}`, then the response returns the current status and the
    complete triage recommendation, including confidence and model version.
14. Given a review request with an unknown action or unsupported replacement value, when
    it is submitted, then the response is HTTP 422 and the queue ticket remains unchanged.
15. Given a ticket that is accepted or changed, when it is queried, then its status is
    the human-review result and it is no longer reported as `awaiting_review`.

## 4. Scope and non-goals

### In scope

- Classification of an incoming ticket into a category, priority, and suggested team.
- A draft first reply that is not sent automatically.
- A queue item with `awaiting_review`, `accepted`, or `changed` status.
- Human acceptance or replacement of the suggested values.
- Model confidence and model version in the externally visible result.
- Validation of request shape and required ticket text.
- Model failure handling for unavailable and timed-out model calls.
- Preservation of near-duplicate submissions as separate queue items.

### Explicitly out of scope

- Automatic email, chat, or other outbound reply delivery.
- Authentication, authorization, user roles, or ownership assignment.
- Durable queue storage across service restarts.
- Semantic duplicate detection or de-duplication.
- Local-language translation, policy lookup, or knowledge-base retrieval.
- Ticket creation in another system or integration with a customer-support platform.
- Automatic retries after `ModelUnavailable` or `ModelTimeout`.
- A human audit trail beyond the current queue status and replacement values.

## 5. Interfaces and contracts

### Create and queue a ticket

`POST /tickets/triage`

Request body:

```json
{
  "subject": "Refund for duplicate charge",
  "body": "I was billed twice for my September membership. Please refund one."
}
```

Successful response, HTTP 201:

```json
{
  "id": "ticket-1",
  "category": "billing",
  "priority": "normal",
  "team": "finance-ops",
  "confidence": 0.86,
  "model_version": "v1",
  "status": "awaiting_review",
  "draft_reply": "Thanks for writing in. I can see the charge you mean and I am checking it now.",
  "reply_sent": false,
  "suggested": {
    "category": "billing",
    "priority": "normal",
    "team": "finance-ops",
    "draft_reply": "Thanks for writing in. I can see the charge you mean and I am checking it now."
  }
}
```

The response's top-level fields are the current queue values. The `suggested` object
contains the original model recommendation so a human decision can be compared with it.

### Retrieve a queued ticket

`GET /tickets/{ticket_id}`

Returns the same queue item shape as the triage response, with the current `status` and
`reply_sent` value. A missing identifier returns HTTP 404 with `ErrorBody`.

### Human review

`POST /tickets/{ticket_id}/review`

Accept:

```json
{
  "action": "accept"
}
```

Change:

```json
{
  "action": "change",
  "category": "billing",
  "priority": "high",
  "team": "finance-ops",
  "draft_reply": "Thanks for writing in. We will investigate the duplicate charge immediately."
}
```

The action must be `accept` or `change`. Replacement fields are optional and are only
accepted when they are valid enum values or text within the stated field limits. A change
must retain the original model suggestion in `suggested` and expose the human values at
the top level.

### Error contract

- HTTP 422 for malformed JSON, wrong field types, missing required text, empty ticket
  content, unsupported review values, or invalid replacement values.
- HTTP 404 for an unknown ticket identifier.
- HTTP 503 when the model is unavailable.
- HTTP 504 when the model times out.
- Every error uses `{ "detail": "...", "code": "..." }`, with repository codes where
  applicable. The response body does not include a synthetic triage result after a model
  failure.

### Model payload

Every successful triage result includes `confidence` as a number from 0 to 1 and
`model_version` as a string. The repository's `ModelPayload` convention is used for these
values, and no low-confidence result is hidden.

## 6. Constraints

- **API shape:** Use the repository's existing Pydantic model and `ErrorBody` conventions;
  request and response shapes must be declared in `app/models.py` rather than crossing the
  API boundary as bare dictionaries.
- **Model access:** Use `app.model_client.get_client()` and catch `ModelUnavailable` and
  `ModelTimeout` around the ticket-classification call.
- **Validation:** `subject` and `body` are strings, and both must contain non-whitespace
  text. Each field is limited to 1,000 characters.
- **Confidence threshold:** A result below 0.50 is low confidence. The score is preserved
  and the item remains queued for human review.
- **Automatic sending:** No reply is sent automatically. A human review action changes the
  queue state and may retain an accepted or changed draft; actual delivery is not part of
  this interface.
- **Queue state:** Initial status is `awaiting_review`; accepted is `accepted`; changed is
  `changed`.
- **Model version changes:** The returned model version is the version used for that
  classification. Queue records must not silently replace it with a later version.
- **Performance:** A single triage request must not exceed the model client's configured
  call limit, and queue retrieval must be constant-time for a single identifier.
- **Compatibility:** The new feature must not alter the existing library list, summary,
  health, or describe endpoints.

## 7. Test plan

- `tests/test_ticket_triage.py::test_ac1_classifies_and_queues_ticket` covers AC1.
- `test_ac2_routes_recognized_categories_to_expected_teams` covers AC2.
- `test_ac3_sets_high_priority_for_urgent_language` covers AC3.
- `test_ac4_handles_general_tickets_without_guessing` covers AC4.
- `test_ac5_preserves_low_confidence_for_human_review` covers AC5.
- `test_ac6_human_accept_keeps_suggestion` covers AC6.
- `test_ac7_human_change_overrides_suggestion` covers AC7.
- `test_ac8_keeps_near_duplicates_separate` covers AC8.
- `test_ac9_rejects_malformed_request_shapes` covers AC9.
- `test_ac10_rejects_missing_ticket_text` covers AC10.
- `test_ac11_returns_503_when_model_is_unavailable` covers AC11.
- `test_ac12_returns_504_when_model_times_out` covers AC12.
- `test_ac13_returns_current_queue_state` covers AC13.
- `test_ac14_rejects_invalid_review_actions` covers AC14.
- `test_ac15_keeps_accepted_or_changed_status_visible` covers AC15.

The tests use the repository's `client` fixture and model-client environment controls.
They assert externally observable HTTP status, response fields, queue state, and error
shape rather than private call paths.

## 8. Open questions

- Should human acceptance trigger an outbound send, or should it only change the queue
  state? This specification currently defines no automatic send and requires a separate
  explicit operation if delivery is introduced.
- Should queue records persist outside the process, and how is ownership assigned?
- Should a human change be an append-only override, or should the original recommendation
  remain visible as `suggested`?
- How should near-duplicate tickets be grouped for a human without auto-deduplicating
  them?
- Should a ticket with both fields empty be HTTP 422, or should it be queued as `general`
  for review?
- Should the public category vocabulary be expanded to include `feature_request`,
  `security`, `privacy`, `accessibility`, or `deletion` in a later version?

# Feature Specification — Support Ticket Triage v2

**Status:** draft  
**Author:** specification author  
**Reviewers:** —  
**Date:** 2026-10-06

---

## 1. Intent

The Support Ticket Triage feature turns an incoming support request into a structured
recommendation and places it in a human-review queue. A human may accept the recommendation
or replace its category, priority, team, or draft reply before the ticket is handled further.
This feature provides a starting point for a support agent; it does not send messages or act as
a fully autonomous responder.

## 2. User stories

- As a support agent, I want a valid ticket to receive a structured category, priority,
  team, confidence, model version, and draft reply so that I can begin review.
- As a support agent, I want low-confidence and uncertain recommendations to remain visible
  and queued rather than being presented as certain.
- As a support agent, I want to accept or replace a recommendation so that the queue records
  the human decision.
- As a support operator, I want to retrieve the current queue state and recommendation for a
  ticket.
- As a support operator, I want malformed ticket input, invalid review data, and model failures
  to produce a documented error instead of an unverified queue item.

## 3. Acceptance criteria

1. Given a valid ticket whose subject and body are non-empty strings, when
   `POST /tickets/triage` is called, then the response is HTTP 201 and contains a ticket
   identifier, category, priority, team, confidence, model version, status
   `awaiting_review`, a non-empty draft reply, and `reply_sent: false`.
2. Given a ticket classified by the model as `billing`, `access`, `data`, or `outage`, when
   it is triaged, then the response exposes the corresponding category and the repository-defined
   team `finance-ops`, `identity`, `data-platform`, or `platform-sre`, together with the
   model's confidence and model version.
3. Given an urgent ticket containing language such as `urgent`, `asap`, `immediately`,
   `blocked`, or `down`, when it is triaged, then the response reports priority `high`.
4. Given a ticket with no recognized category or urgent signal, when it is triaged, then the
   response reports category `general`, team `triage`, and priority `normal` or `low` according
   to the model result. The response must not invent a category or team.
5. Given a model result with confidence below `0.50`, when the ticket is triaged, then the
   response preserves the score, marks the queue item `awaiting_review`, and does not send the
   draft reply automatically.
6. Given a queued ticket, when a human calls `POST /tickets/{ticket_id}/review` with
   `action: accept`, then the queue status is `accepted`, the suggested values are retained,
   and `reply_sent` remains `false`.
7. Given a queued ticket, when a human calls `POST /tickets/{ticket_id}/review` with
   `action: change`, then the queue status is `changed`, each supplied replacement is returned
   at the top level, omitted fields retain their current values, and the original model
   recommendation remains available in `suggested`.
8. Given two separately submitted near-duplicate tickets, when both are triaged, then each
   receives a distinct ticket identifier and remains in the queue. The feature must not
   auto-merge, auto-close, or suppress either item.
9. Given a request whose JSON body is not an object, whose `subject` or `body` is not a
   string, or whose field length exceeds 1,000 characters, when it is submitted, then the
   response is HTTP 422 and contains the repository `ErrorBody` shape.
10. Given a ticket with an empty or whitespace-only subject or body, when it is submitted,
    then the response is HTTP 422 and no queue item is created.
11. Given a valid ticket and a model that raises `ModelUnavailable`, when triage is attempted,
    then the response is HTTP 503 with `ErrorBody`, and no queue item is created.
12. Given a valid ticket and a model that raises `ModelTimeout`, when triage is attempted,
    then the response is HTTP 504 with `ErrorBody`, and no queue item is created.
13. Given a queued ticket, when its current state is requested with
    `GET /tickets/{ticket_id}`, then the response returns the current status, the complete
    recommendation, confidence, and model version. A missing ticket identifier returns HTTP
    404 with `ErrorBody`.
14. Given a review request with an unknown action or an unsupported replacement value, when it
    is submitted, then the response is HTTP 422, the queue ticket remains unchanged, and the
    response contains `ErrorBody`. Unsupported values include an invalid category, priority,
    team, an empty draft reply, or a draft reply longer than 1,000 characters.
15. Given a ticket that is accepted or changed, when it is queried, then its status is the
    human-review result and it is no longer reported as `awaiting_review`.

## 4. Scope and non-goals

### In scope

- Classification of an incoming ticket into a category, priority, and suggested team.
- A draft first reply that is not sent automatically.
- A queue item with `awaiting_review`, `accepted`, or `changed` status.
- Human acceptance or replacement of the model recommendation.
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

Acceptance is a queue-state transition only. It does not cause a reply to be sent. A later
feature may introduce a separate explicit send operation, but that operation is not part of
this feature.

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

The top-level recommendation is the current queue value. The `suggested` object preserves the
original model recommendation for comparison with a human decision.

### Retrieve a queued ticket

`GET /tickets/{ticket_id}`

Returns the same queue-item shape as the triage response, with the current `status` and
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

The action must be `accept` or `change`. A change may provide any subset of the replacement
fields. Each supplied value must be valid, and each omitted value retains the current queue
value. The original model recommendation remains in `suggested` after either review action.

### Error contract

- HTTP 422 for malformed JSON, wrong field types, missing required text, empty ticket content,
  unsupported review actions, or invalid replacement values.
- HTTP 404 for an unknown ticket identifier.
- HTTP 503 when the model is unavailable.
- HTTP 504 when the model times out.
- Every error uses `{ "detail": "...", "code": "..." }`. The repository error codes apply
  to validation, not-found, model-unavailable, and model-timeout responses.
- A model failure must not create or return a synthetic queue item.

### Model result contract

Every successful triage result includes `confidence` as a number from 0 to 1 and
`model_version` as a non-empty string. The confidence and version belong to the model
classification that produced the queue item and must not be replaced by a later model result.
A low-confidence result remains visible and queued; it is not treated as a validation error.

## 6. Constraints

- Request and response shapes are declared as typed models; API responses do not cross the
  boundary as bare dictionaries.
- Ticket text is limited to non-whitespace strings of at most 1,000 characters each.
- The public category values are `billing`, `access`, `data`, `outage`, and `general`.
- The public priority values are `high`, `normal`, and `low`.
- The public team values are `finance-ops`, `identity`, `data-platform`, `platform-sre`, and
  `triage`.
- The queue state values are `awaiting_review`, `accepted`, and `changed`.
- Confidence below `0.50` is low confidence. The score is preserved and the item remains
  queued for human review.
- No reply is sent automatically. Human acceptance changes the queue state only.
- A model version change may change the recommendation, confidence, or team. The queue item
  retains the version used to create that item.
- Queue lookup is scoped to a single identifier. The queue is process-local and does not
  persist across service restarts.
- Near-duplicate requests are independent queue items; semantic duplicate detection is not
  required.
- The feature must not change existing library, summary, health, or describe endpoints.

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

The tests use the repository's `client` fixture and model-client environment controls. They
assert externally observable HTTP status, response fields, queue state, and error shape rather
than private implementation details.

## 8. Open questions

- Should a future version add an explicit send operation, and if so, what action or request
  shape should perform it?
- Should queue ownership or human identity be added in a future version?
- Should queue records be persisted in a future version?
- Should the public category vocabulary be expanded with values such as `feature_request`,
  `security`, `privacy`, `accessibility`, or `deletion`?

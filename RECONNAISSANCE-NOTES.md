# Support Ticket Triage — Reconnaissance Notes

## Scope and approach

This is a temporary design exploration only. It does not implement the feature or change
existing application code. The proposed behavior is derived from the repository's existing
model-client, model-payload, error, and HTTP-test conventions.

## Important unstated assumptions

### Categories

- The model's task currently produces only `billing`, `access`, `data`, `outage`, and
  `general`; the six category values are the public contract for this feature.
- The model may assign `general` to ambiguous, unsupported, or low-keyword tickets.
- A `general` result is not treated as a validation failure; it remains a queue item for
  human review and can be routed to the general `triage` team.
- The specification must not assume that a category is semantically certain merely because
  the model returned one.

### Priority levels

- The public priority values are `high`, `normal`, and `low`.
- `high` is used for urgent, blocked, or service-disruption language.
- `normal` is used for a matched category with no explicit urgent signal.
- `low` is used only for an unrecognized or low-confidence result in the current stub.
- A human review action may override the suggested priority; the model's result remains
  metadata rather than an irreversible decision.

### Team routing

- The model routes the four recognized categories to `finance-ops`, `identity`,
  `data-platform`, and `platform-sre`; unrecognized categories route to `triage`.
- The team is a recommendation, not an authorization or access-control decision.
- A human may replace the suggested team during review. The team must be visible in the
  queue response and in the review result.

### Confidence and low-confidence behavior

- The model returns a confidence score in the range 0 to 1 and a model version.
- A confidence below 0.50 is low confidence. The feature must preserve the score and
  return it to the caller rather than hiding it.
- Low-confidence results remain queued for human review and must not be sent automatically.
- The current model returns confidence 0.44 for ambiguous matches and 0.33 for degraded
  output. The specification should not create a new confidence threshold from the fixture
  alone; 0.50 is the repository's existing low-confidence convention.

### Human review and automatic replies

- Every triage result is placed in a human-review queue. The response includes a draft
  first reply, but that draft is not an outbound message.
- No automatic reply is sent by this feature. A human must explicitly accept or change
  the triage and, if the product also supports an actual send operation, that send must be
  a separate explicit action.
- Human review may override category, priority, team, and draft reply. The original model
  predictions remain available as evidence and are not overwritten in the audit record.
- A human-accepted item is distinguishable from a human-changed item in queue status.

### Duplicate tickets

- Each submitted ticket is retained as a separate queue item, even when its text is near-
  duplicate of another ticket.
- The feature does not auto-merge, auto-close, or deliberately deduplicate near-duplicates.
- A human may see the same underlying problem more than once and may make separate
  decisions. The queue's identifier must be stable for that specific submission.
- Exact duplicate input is not defined as a separate error because the feature does not
  currently have a ticket identity or deduplication policy.

### Validation and malformed input

- The request must contain a string `subject` and string `body`.
- Both fields must contain non-whitespace text; the fixture's missing subject and missing
  body cases are treated as invalid input rather than as general tickets.
- Subject and body lengths need finite limits so a one-call request cannot become an
  unbounded model prompt. The initial proposal is 1,000 characters for each field.
- Invalid JSON, non-object bodies, wrong field types, unsupported enum values, and values
  over length limits return HTTP 422.
- Unsupported model result values are not treated as arbitrary user input; they are handled
  as model data failures or queue decisions.

### Model failures and queue availability

- `ModelUnavailable` produces HTTP 503 and no queue item.
- `ModelTimeout` produces HTTP 504 and no queue item.
- The response must preserve the model's confidence and model version when a model result
  is returned, including low-confidence results.
- A model failure is not represented as a synthetic `general` ticket because that would
  hide the service failure.
- The first implementation does not need retry, circuit-opening, or failure persistence;
  those are open questions for later revisions.

### Queue status and overrides

- Initial status is `awaiting_review`.
- Human acceptance produces `accepted` and retains the accepted suggestion.
- Human replacement produces `changed` and retains the replacement values.
- The queue response exposes the current status and whether a reply has been sent.
- The only supported review actions are `accept` and `change`.
- Review requests must include a reason or reviewer identity only if the product requires
  an audit trail; this feature can initially leave that as an open question.

### Edge cases

- A ticket can contain only an urgent phrase and no recognizable topic. The model can
  return `general`, low confidence, and `triage`; it still queues for review.
- Accessibility, privacy, security, feature-request, and deletion tickets are not
  interpreted as automatic policy decisions. They are queued as `general` until a human
  decides how to route them.
- Model version changes can change the category, priority, team, draft, or confidence.
  The response carries the version used for the result, and the queue record keeps it.
- The feature does not implement authentication, authorization, persistence, outbound
  email, or actual network delivery in this version.
- The initial public contract should use the existing `ErrorBody` shape and status codes,
  with FastAPI validation for malformed request bodies.

## Proposed public contract

- `POST /tickets/triage` accepts `subject` and `body` and returns a queued item.
- `GET /tickets/{ticket_id}` returns the current queue state.
- `POST /tickets/{ticket_id}/review` accepts `action`, optional replacement fields, and
  returns the updated queue item.
- Model-backed responses include `ModelPayload` so callers can see confidence and the
  model version.
- Error responses use `ErrorBody` with the repository's existing codes: `422`, `503`, and
  `504`.

## Decisions to make in the specification

The specification should explicitly resolve these assumptions rather than leave them to an
implementation agent:

1. Whether a human acceptance is only a state transition or also triggers a send.
2. Whether queue records persist across API restarts.
3. Whether an actual reply can be sent through this API or only be handed to a human.
4. Whether duplicate detection uses semantic similarity or simple string matching.
5. Whether human review overrides are append-only audit data or replace the current queue
   values.
6. Whether review endpoint authorization is required for the assignment.

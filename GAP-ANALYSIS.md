# GAP-ANALYSIS: Specification-Driven Development

## Scope and evidence

This analysis uses the repository evidence available on 2026-10-06. The required evidence set includes the ticket-triage specifications and handoff logs, the filtered-summary round used to demonstrate round 1 and round 2, the acceptance tests, and the final current test run.

The repository contains two related-looking artifacts that must be kept distinct:

- `specs/spec-v1.md` and `specs/spec-v2.md` define support ticket triage.
- `demo/spec-v1.md` and `demo/spec-v2.md` define the filtered-summary round whose round-1/round-2 comparison is documented in `demo/README.md` and `demo/REVIEW-NOTES.md`.

The final report therefore treats the ticket-triage handoff evidence as the first-blind-handoff record and the filtered-summary exercise as the round-1/round-2 failure exhibit.

## 1. Reconnaissance assumptions that were not stated

The reconnaissance notes in `RECONNAISSANCE-NOTES.md` identify several assumptions that were not explicitly fixed by the ticket-triage specification. The most important were:

- The model currently produces only `billing`, `access`, `data`, `outage`, and `general`; these are the public category contract.
- `general` may be returned for ambiguous or unsupported tickets but is not evidence that the model is certain.
- The public priority values are `high`, `normal`, and `low`; urgent language maps to `high`, a matched category without an urgent signal maps to `normal`, and low priority is used for an unrecognized or low-confidence result.
- The model's confidence range is 0 to 1, with 0.50 as the repository's low-confidence convention.
- Every triage result enters human review. The draft reply is not sent automatically.
- Human review may replace category, priority, team, or draft reply, while the original model recommendation remains available as `suggested`.
- Near-duplicate submissions remain separate queue items; there is no semantic duplicate detection or auto-merge.
- Empty subject/body values are invalid rather than `general` tickets.
- `ModelUnavailable` and `ModelTimeout` must produce HTTP 503 and 504 respectively, with no queue item.

These assumptions are important because the repository's reconnaissance notes say they were derived from the existing model client and conventions, not stated as explicit requirements. The v1 specification's user stories and acceptance criteria do not fully explain the public vocabulary, confidence threshold, or human-review behavior. The v2 specification resolves some of those gaps, but it still leaves durable storage, ownership, and future send behavior open.

## 2. First blind handoff: criteria that passed and failed

### Ticket-triage handoff

The first ticket-triage handoff is documented in `logs/handoff-1.md`. Its initial test attempt did not run because `make` was unavailable, then the active Python environment lacked FastAPI. After creating the intended virtual environment and installing the declared requirements, the focused ticket suite reported 21 passing cases. The final full run reported 74 passed and 0 failed.

No acceptance-criterion failure was recorded for the ticket-triage handoff. The log therefore supports the following result: AC1 through AC15 were implemented and passed in the final repository state, although the first test invocation was blocked by environment setup rather than by a behavioral failure.

The log also records a cleanup after the first full run: duplicate route-level enum aliases were removed. The final implementation retained the shared model declarations and did not change the specification files.

### Filtered-summary round

The prepared round-1 exhibit is different from the ticket-triage handoff. `demo/README.md` states that round 1 produced 5 of 8 acceptance criteria failures, and `demo/REVIEW-NOTES.md` identifies the three root problems: the cache key was unspecified, “concise” had no measurable definition, and empty-result/model-failure paths were absent.

The repository evidence therefore supports the following round-1 result:

- AC1: passed.
- AC2: failed because “concise” was not enforced and the model could return more than the intended limit.
- AC3: failed because a single global cache did not establish that the cache was keyed to a particular filter set.
- AC4: failed because the specification did not define an empty-result path or state that the model must not be called.
- AC5: failed because a global cache could return the first filter's summary for a different filter.
- AC6: failed because no model-failure behavior was specified; the implementation would need to degrade with `summary: null` and `model_error` rather than return 5xx.
- AC7: the prepared v1 draft contained only four criteria and did not assign a separate AC7 result. The v2 spec adds the model confidence and model version requirement.
- AC8: not present in v1; the prepared evidence describes the v1 draft as having only four criteria. The later v2 test suite contains seven criteria, with AC6 tested through both model failure and timeout cases.

The supplied `demo/README.md` says round 2 passed all eight acceptance-test cases, covering seven criteria with two AC6 cases. The current final `app/routes/summary.py` and `tests/test_summary.py` show the round-2 implementation and direct mapping to those criteria.

## 3. Specification gaps and v1-to-v2 wording

### Cache scope and correctness

**v1 wording:**

> “The summary is cached, so repeated requests do not re-run the model.”

**v2 wording:**

> “Given the same normalised filter set is requested twice inside the cache window, when the second request arrives, then it returns the first response's summary, `cached` is `true`, and **the model is not called a second time**.”

The v1 wording does not say what is cached or whether requests with different filters share a cache entry. The v2 wording fixes both the key and the expected cache hit. It also makes the cache a per-normalised-filter-set entry rather than a global cache.

### Summary length

**v1 wording:**

> “The summary is concise.”

**v2 wording:**

> “Given the model returns a summary longer than 60 words, when it is returned to the caller, then it is truncated at a word boundary to at most 60 words and `truncated` is `true`. `word_count` always reports the returned length.”

“Concise” is not measurable. The revised criterion supplies a server-side limit, a word-boundary rule, and an observable response field. The final implementation enforces this limit in `app/routes/summary.py`.

### Empty selections and model failures

The v1 draft did not contain explicit criteria for either path. The relevant v2 wording is:

> “Given a filter matching zero rows, when the endpoint is called, then `count` is `0`, `summary` is `null`, and **the model is not called at all**.”

> “Given the model raises `ModelUnavailable` or `ModelTimeout`, when the endpoint is called, then the response is still HTTP 200 with `summary` is `null` and `model_error` set to a short reason. **The endpoint never returns 5xx because the model failed.**”

These additions are the missing specification behavior. Without them, round-1 code could call the model on an empty selection or allow model errors to escape as server errors.

## 4. What round 2 still got wrong, if anything

The prepared evidence says round 2 passed all eight acceptance-test cases, and the current `tests/test_summary.py` has eight test functions, with AC6 represented by two cases. The final implementation also includes the following intentional boundaries:

- Cache misses for the same filter may execute concurrently; the specification explicitly declares single-flight out of scope.
- The model version is not part of the cache key, so a cached v1 response can be served after a v1-to-v2 switch during the cache window.
- Cache invalidation when rows are edited is out of scope.
- Stale-cache versus fresh-response behavior is an unresolved open question.

These are not documented as round-2 failures. They are specification choices left for later work. A hypothetical v3 should make the stale-cache policy and cache invalidation policy explicit rather than leaving them as open questions.

For the ticket-triage feature, the v2 specification still leaves durability, ownership, and the exact future send operation unresolved. The repository's reconnaissance notes also state that queue persistence, review authorization, and append-only audit behavior should be resolved in the specification rather than inferred by an implementation agent.

## 5. Where the specification went too far

The ticket-triage v1 specification attempted to define the public category, priority, team, confidence, and queue-state vocabulary as API behavior. Some of this belongs to the implementation contract, but the critical distinction is that the specification should define externally observable behavior and constraints, while the implementation should choose internal data structures and descriptive error text.

The v1 text that went too far was its inclusion of detailed route and model implementation guidance, including the requirement to use the repository's model-client call path and to expose typed models. Those are repository conventions that should be followed, but they are not user-facing requirements. The safer split is to specify the response fields, status codes, validation rules, and queue transitions while allowing the implementation to decide how to store the queue internally.

The filtered-summary v2 specification also went too far in making the cache implementation process-local and limiting it to ten minutes. Those are implementation policy choices, although the specification must state the externally observable cache behavior and a cache lifetime if it wants repeatable behavior. The current repository keeps the implementation in `app/routes/summary.py`, while the specification remains the source of the public contract.

## 6. Submission verification

The required evidence is present as follows:

- `specs/spec-v1.md` — present.
- `specs/spec-v2.md` — present.
- Round-2 implementation — `app/routes/summary.py` and the ticket route at `app/routes/tickets.py` are present.
- Tests mapped to acceptance criteria — `tests/test_summary.py` and `tests/test_ticket_triage.py` provide `test_ac1_` through `test_ac15_` mappings.
- `logs/handoff-1.md` — present.
- `logs/handoff-2.md` — present.
- `GAP-ANALYSIS.md` — this file.

A repository-wide secret scan found one obvious API-key-like value in `data/diffs/02-has-a-real-bug.diff`: `sk-live-4f9a2c7e11b8`. It is a sample-looking string that should not be committed as a real credential. The repository also contains ordinary password-related text in test data, but no additional production API key, bearer token, private key, or confirmed secret was found in the requested submission evidence. The fake credential should still be removed or replaced before submission if the assignment permits editing the diff fixture.

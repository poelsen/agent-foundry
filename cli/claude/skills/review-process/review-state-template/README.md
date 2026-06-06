# Review State

This directory is the durable state store for the review-process family.

Use it when a review produces state that must survive the current
conversation:

- recurring finding tags;
- converted checks;
- deferred findings;
- accepted risks;
- review-process self-audit notes.

## Required fields for state entries

Append entries to `log.md` using this shape:

```text
## <entry-id>: <title>

Type: FINDING | CONVERTED_CHECK | DEFERRAL | ACCEPTED_RISK | PROCESS_NOTE
Source review: <artifact or review ID>
Tag: <domain/class tag>
Status: OPEN | RESOLVED | EXPIRED
Owner: <person/team/agent, or not-assigned>
Trigger: <event that reopens/reviews this entry>
Evidence: <link/path/command/output>
Action: <what was done or must be done>
Verification: <how to prove the check/action still works>
```

## Tag guidance

Use stable tags so future reviews can search recurrence:

- `docs/drift`
- `docs/navigation`
- `process/reviewer-routing`
- `process/over-review`
- `process/under-specified`
- `tests/mock-integration`
- `tests/missing-failure-path`
- `architecture/ownership`
- `architecture/dual-api`
- `threading/ui-blocking`
- `threading/stale-worker`
- `persistence/migration`
- `dependencies/stale-direct`

Add new tags only when no existing tag fits.

## Review-state checks

Before T2+ reviews, search `log.md` for tags matching the scope. Before T4
reviews, also inspect all OPEN entries and state whether each was resolved,
expired, or remains accepted/deferred.

# PRP: Walmart monitor projection for Listing Management

```text
Status: APPROVED_BY_OWNER
Approved: 2026-10-27
Implementation branch: feat/listing-real-evaluation-readonly-preview-20261027
```

## Goal

Parse accepted monitor RAW events into immutable typed observations, maintain a replayable current
monitor projection, and overlay approved non-empty monitor values in the existing Listing
Management API. Use daily monitor observations as strike-price and buy-box evidence for the
diagnostic Listing lifecycle evaluator.

## Scope

- Add L3 observation and L9 current-projection tables in a new Alembic revision.
- Project every stable target identity from a newly accepted RAW event in the same database
  transaction. A monitor check is item-page scoped, while one Item can map to more than one
  account/store Listing identity.
- Provide a controlled local/operations replay CLI for already accepted RAW events.
- Overlay the approved Listing fields without mutating the existing Listing MART.
- Keep outcome/source/error/image/RAW identifiers out of the frontend response.
- Fix PR #260 rule-version consistency, lifecycle eligibility, pagination, schedule-boundary and
  advisory-lock correctness while this branch is still draft.

## Explicit non-goals

- No production migration, deployment, RAW replay or external API call.
- No change to the monitor producer or its category alert implementation.
- No inference of a hijack decision from seller-count fields.
- No formal publication of Listing grades while financial completeness remains blocked.
- No modification of `old-system/`.

## Acceptance

- Exact RAW replay is idempotent across RAW, observation and current projection.
- The newest observation wins; its absent fields fall back to the existing Listing read model.
- Listing API uses monitor values first and existing MART values as fallback.
- Filters and summary counters use the same effective values shown in rows.
- Diagnostic evaluation uses one immutable rule version for an entire batch.
- Excluded lifecycle stages never receive an A-D candidate.
- Batch pagination does not use OFFSET.
- Tests cover parsing, precedence, scheduler boundaries, lock ownership and batch invariants.

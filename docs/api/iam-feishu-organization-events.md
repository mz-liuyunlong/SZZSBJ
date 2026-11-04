# IAM / Feishu encrypted organization event ingestion (PR #287)

Status: **code implemented, unverified; not enabled or deployed**. The event receiver,
worker and schema are scoped exclusively to PR #287. Do not treat this document as
authorization to configure real Feishu tenants, perform provider calls or migrate
production.

## Authority and data source

- External source: Feishu Contact events and Feishu Contact directory.
- Event callback: `POST /api/integrations/feishu/organization-events`.
- Organizational authority: **fresh Feishu directory** loaded by
  `FeishuDirectoryService`; event content is *only a change signal*.
- Local canonical snapshot: `iam_feishu_departments`,
  `iam_feishu_employees`, `iam_feishu_org_sync_runs`.
- Event inbox: `iam_feishu_org_events` (migration
  `20261104_0073_feishu_org_events` after `20261102_0072_org_owner_bindings`).
- The inbox never stores ciphertext, callback JSON, token, verification string,
  employee name, or full event object. It stores event ID, event type, optional
  Feishu `open_id`, state, attempts, times, last error category and reconciliation
  run reference. An event ID is unique; repeated delivery does not duplicate work.

## Security boundary

1. Global anonymous access is waived **only** for the exact POST callback path.
2. Receiver is default disabled by `SZZSBJ_FEISHU_ORG_EVENTS_ENABLED=0`.
3. With the receiver enabled, `FEISHU_ORG_EVENT_ENCRYPT_KEY`,
   `FEISHU_ORG_EVENT_VERIFICATION_TOKEN` and existing `FEISHU_APP_ID`
   are required. Their values must come from approved secret storage, never Git.
4. Accept only a bounded (`64 KiB`) encrypted body with valid timestamp,
   nonce, signature, AES-CBC payload, verification token and application ID.
   Verify the received raw bytes before decrypting. Reject plaintext events.
5. The timestamp may not be in the future by more than five minutes or older
   than seven hours. A verified, encrypted URL challenge is returned unchanged.
6. Only an allowlist of contact user/department/scope events enters the inbox.
7. Verified user deletion/freeze/resignation/deactivation events immediately
   revoke active `app_sessions` for matching `app_users.feishu_open_id`,
   transactionally with inbox insertion. An event-level `revoke_session` marker
   also blocks new logins and existing sessions until a later accepted directory
   snapshot supersedes it. This **does not delete the account** and does not
   assign or modify a role.
8. Successful non-offboarding callbacks never alter data authorization directly.
   They trigger a fresh directory reconciliation through the worker.

## Delivery and reconciliation

- `iam.organization_event_tick` runs at a 60-second schedule but is a no-op
  until **both** `SZZSBJ_FEISHU_ORG_EVENTS_ENABLED=1` and
  `SZZSBJ_FEISHU_ORG_AUTO_SYNC_ENABLED=1` are explicitly configured.
- The inbox claims up to 25 due events using PostgreSQL
  `FOR UPDATE SKIP LOCKED`, and marks them `processing`.
- It reads the current complete Feishu directory, verifies the canonical
  snapshot, applies under the existing advisory lock and records the run ID.
- A successful reconciliation marks the batch `applied`. A transient failure
  retries with exponential delay up to six attempts; unsafe directory
  replacement, shrink, incomplete visibility or invalid hierarchy moves the
  batch to `needs_review` without overriding snapshot safety checks.
- A crashed consumer's processing lease can be reclaimed after 15 minutes.
- No event may bypass the existing full-snapshot 20% identity guard.

## Administrator operations

- `GET /api/settings/organization/event-inbox`: super-administrator only,
  optionally filter by one allowed status, at most 100 recent event records.
- `POST /api/settings/organization/event-inbox/retry`: super-administrator
  only; explicit confirmation phrase, 1–50 event IDs; transitions only
  `needs_review` to `pending` transactionally. It does **not** run provider
  calls or override directory safety. Requires the worker enable switches for
  later execution.
- Organization page displays inbox status and reviewed retry action when
  `canSync` is true. Existing organization snapshot and owner-binding pages
  remain the same.

## Not yet verified or authorized

- No real Feishu callback or webhook configuration has been performed.
- No production migration has been applied.
- No pytest, frontend build, PostgreSQL acceptance or end-to-end callback
  verification has been run for this change.
- The official event version, encrypted URL verification envelope and account
  field semantics require integration acceptance in a controlled Feishu test
  tenant before enabling.
- This implementation is an event-driven **full-directory reconciliation**,
  not a field-level employee patch/CDC source of truth.
- Manual-review events must be investigated for lost Feishu visibility and
  unexpected identity replacement before retry.

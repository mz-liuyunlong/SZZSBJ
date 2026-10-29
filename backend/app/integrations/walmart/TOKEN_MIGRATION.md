# Walmart Mac scheduler -> SZZSBJ cloud credential migration (draft)

Status: **code foundation only; production disabled. No live Walmart calls performed.**

## Accepted architecture

1. SZZSBJ owns the scheduler, queue, approved store_id mapping and remote task lifecycle.
2. The *existing* eight (now nine requested) per-store servers execute Walmart business APIs with independent exit IPs. They must never receive a Client Secret.
3. Account B Tencent SSM stores one Walmart Client ID and Client Secret per store.
4. An owner-deployed SCF Token Broker obtains a short-lived access token for its bound store and returns it to a **strictly trusted internal scheduler process**.
5. The scheduler passes the token to the pre-existing per-store worker over a protected SSH stdin channel. Do not place tokens into a Celery task payload, result backend, DB, HTTP response, command-line flag or log.
6. CN2502 is **enabled in the planned nine-store scope**. Its actual server identity / IP is NOT verified in the 2026-10-23 handoff and must be explicitly registered before live dispatch; never guess or fail over.

## Source alignment

The 2026-10-23 handoff describes `features/tools/walmart_remote_pull/scheduler.py`,
`run_worker.py`, `batch_state.py` and `convert.py`. Their **full sources are
supplied separately by the user but not committed to the SZZSBJ repository** and must be obtained before
a faithful SSH scheduler/data-conversion port can be completed.

The existing `scf_runtime.py` / `https_transport.py` perform the *wrong*
deployment responsibility (SCF calls Walmart business APIs). They are
**intentionally unchanged** and the existing server-side SCF read feature gate
must stay off. Use the separate `token_broker.scf_token_handler` under an
owner-controlled deployed entrypoint only after IAM and invocation review.

## Security / prerequisites (must block activation)

- The main server role may only Invoke allowlisted per-store SCFs; it must
  never read Tencent SSM or modify cloud functions, roles, policies or aliases.
- Each SCF execution role must only GetSecretValue for its own store. Static
  role attachment was NOT validated by the earlier audit because role names
  were not parsed. Audit effective policies and permission boundaries.
- Developers must not have the ability to deploy arbitrary production SCF
  code, assume the security owner role or obtain root/production code execution
  on the protected scheduler/child workers; otherwise short-lived tokens can be
  intercepted. The main server token-bearing process must be owner controlled.
- No SCF public triggers or Function URLs, no token-bearing logs, no shared
  store credential fallback. Store-bound SCF names and stable versions only.
- Do not publish or invoke Token Broker until its Walmart `/v3/token` request
  origin has been verified against the store's Walmart IP allowlist. The
  SCF public network is not equivalent to the existing child server's IP.
  If the SCF source IP is not allowed, use an owner-controlled token exchange
  path over that store's fixed egress without transmitting the Client Secret
  to a developer-controlled host. This needs separate implementation/review.
- Token duration is capped at 900 seconds; expire in memory earlier than the
  provider expiry. One token does not imply operation-level authorization.
- Start with an authorized read-only store, verify end to end, then roll out.

## Files added in this branch

- `token_broker.py`: SCF-only, store-bound, opt-in token issuance, no long-term secret return.
- `token_client.py`: main-server typed response validation and isolated SCF invocation.
- `test_token_broker_migration.py`: offline cross-store, forged result, sensitive repr tests.


## Original 2026-10-26 code package (confirmed available)

The user has supplied `walmart-remote-pull-it-pack-20261026.tar(3).gz`.
It contains original `features/tools/walmart_remote_pull/scheduler.py`
(v1.3.0), `run_worker.py` (v1.3.2), `batch_state.py`, 2 mock test
modules, and `features/tools/walmart_to_daily/convert.py`. This supersedes
earlier statements that the original source was unavailable.

The original worker expects `--collect --store-id --run-id
--remote-tmp-dir --endpoints --date --window-days --output-mode
--min-interval-ms`, with optional `--gtin-file`; short-lived token on
stdin only. The legacy scheduler also creates an atomic remote
`.runs/<run_id>` lock **before token acquisition**, uploads
`run_worker.py` to `<remote_tmp_dir>/<run_id>/run_worker.py`,
transfers/hash-checks optional GTIN input, recovers ambiguous SSH
outcomes by inspecting remote status (never blindly retries), retrieves
artifacts, validates manifest and hashes, and cleans the remote run only
after verified success. It does not place credentials on workers.

**Important safety boundary:** The current `remote_dispatch.py` now uses
the original worker argv, and `remote_pipeline.py` passes the persisted
`store_id`, but the full original scheduler/worker source has **NOT**
been committed into this repository and the protected worker upload /
lock / GTIN handshake is not complete. Do not enable remote collection
until these source-level steps are ported and tested, or the process may
fail after receiving a short-lived token. CN2502's dedicated route is
still unverified. Do not copy any `.secrets/` values or SSH private
keys into Git.

## Implemented in branch (requires integration acceptance)

- Cloud-bound Token Broker and typed STS/SCF client.
- Nine-store strict SSH route parsing (CN2502 required) and token-only-in-stdin process adapter.
- SCP retrieval with SHA256SUMS and manifest verification; server cleanup is intentionally not automatic.
- Durable PostgreSQL job model, Alembic migration (NOT APPLIED), gated Celery dispatch and scoped FastAPI endpoints.
- A data-center Walmart collection page for manual read-only task creation and job status refresh.

## Not yet implemented or enabled

- Faithful port of colleague Mac scheduler and remote worker: their full original source
  and exact worker CLI/output schema were not supplied. The new adapter assumes
  a documented run-id/operations CLI and fixed run directory; it requires
  validation against the real installed worker before dispatch is safe.
- CN2502 child server address and its Walmart allowlist verification.
- Automatic schedule/recovery rules and data conversion into SZZSBJ business tables.
- Backfill and cleanup behavior pending original scheduler source and owner approval.
- Migration must be reviewed against the production DB revision graph before applying.
- Production CAM permission checks and safe SCF deployment.
- End-to-end tests and production cutover.

Do **not** turn on `SZZSBJ_WALMART_SCF_READ_ENABLED` or
`SZZSBJ_WALMART_SCF_TASKS_ENABLED` for this migration.


## Token-free recovery and optional cleanup (2026-10-29)

Implemented `remote_recovery.py` and `walmart_remote.recover`, callable only for
a persisted `needs_review` run through the RBAC-scoped
`POST /api/integrations/walmart-remote/jobs/{job_id}/recover` endpoint.
This path does **not** request Token Broker credentials, generate a new run ID
or start the worker; it must find an existing manifest v2 with exact store,
run ID, and endpoints. An incomplete prior local download is moved to a
unique `.partial-*` location for inspection, then the same remote run is
downloaded and checksum-verified. Existing converted output is checked by
SHA256 instead of overwritten. The frontend exposes **只回收** on
`needs_review` rows.

Successful output conversion invokes `cleanup_verified_run` only when
`SZZSBJ_WALMART_REMOTE_CLEANUP_ENABLED=1`; disabled by default. It
verifies the archived manifest hash against the remote before deleting
the particular run directory and **never** deletes `.runs/<run_id>`
state/lock evidence. Enable only after owner approval and real host tests.

**Not yet production-accepted:** multi-store concurrency, recovery after
Celery worker process death, nine-store end-to-end mocks and real API
runs, and writes into product/inventory business tables. No changes to
production credentials, live jobs, or database were performed.

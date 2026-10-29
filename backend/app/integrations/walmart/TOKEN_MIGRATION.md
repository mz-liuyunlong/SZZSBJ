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
not currently present in the SZZSBJ repository** and must be obtained before
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

## Not yet implemented or enabled

- Real Mac scheduler source port, SSH transport, worker execution, SHA256
  manifest validation, durable task state / DB and UI.
- CN2502 child server address and its Walmart allowlist verification.
- Production CAM permission checks and safe SCF deployment.
- End-to-end tests and production cutover.

Do **not** turn on `SZZSBJ_WALMART_SCF_READ_ENABLED` or
`SZZSBJ_WALMART_SCF_TASKS_ENABLED` for this migration.

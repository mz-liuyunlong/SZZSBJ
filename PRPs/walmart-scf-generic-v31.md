# Walmart SCF V3.1 — owner-approved implementation

Owner authorization: 2026-11-25; create one Git branch, implement the full approved generic internal transport, commit and prepare a PR. Base: 0d438c101d44a733e551fe2d6ab9ca82046d5895. Branch: feat/walmart-scf-generic-20261125.

## Goal and scope

Keep nine independent functions and SSM secrets. Add a trusted backend-only generic call accepting store, method, relative path, query, JSON body and response format. No business catalog registration, risk classification, approval reference, audit-success gate or business ledger is required by this new channel. Preserve existing v1/v2/v3 and existing business authorization and workflows. No public generic route, new DB, migration, real provider calls, production configuration or unrelated business changes.

## Architecture and data source

Existing official Walmart Marketplace API via existing per-store SCF/SSM; no new business dataset or data source. Event version 4 is independently domain-separated and signed using the existing Ed25519 identity. Verify store/function binding, full payload, expiry and replay, enforce fixed official HTTPS origin, safe relative path, bounded transport and secret exclusion. Reuse existing CAM/STS, key and approved network configuration. Existing business permissions remain in their existing routes. No frontend.

## Validation and rollback

Offline tests for all five methods, arbitrary new operation, JSON/PDF/ZIP, provider error, tampering, cross-store, expiry, replay, credential echo, unsafe paths, response limits, all nine routes and Python 3.10 bundle. Run applicable preflight and existing tests; record actual results only. Deploy later with explicit production authorization, first CN2601 canary then other stores; restore recorded stable alias on failure. Shared replay configuration must be verified before claiming cross-instance protection. No automatic ambiguous write retry.

See backend/app/integrations/walmart/INTEGRATION.md for internal API, limits, deployment and rollback. Status: implementation candidate, not approved for merge/deployment.

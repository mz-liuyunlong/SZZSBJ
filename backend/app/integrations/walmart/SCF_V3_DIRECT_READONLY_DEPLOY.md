# Walmart SCF v3 direct-public read-only deployment (Python 3.10 target)

Status: **code-only development branch**, not deployed. Production `stable`, SSM, existing credentials and store networking remain untouched.

## Existing deployment to preserve
- One SCF per store, each with a store-bound execution role and secret `walmart-<STORE>`.
- Existing v1: `SZZSBJ_WALMART_EGRESS_MODE=direct-public-readonly`, `SZZSBJ_WALMART_DIRECT_PUBLIC_APPROVED=1`, `SZZSBJ_WALMART_LIVE_MODE=owner-approved-read-only`.
- Existing `stable` aliases remain on previously published versions until one-store isolated acceptance.

## New read-only v3 adapter
- `scf_runtime._transport_from_env` selects `WalmartDirectReadOnlyTransport` only with **both** direct-public opt-ins and read-only live mode.
- The adapter requires matching bound store, GET with no body, `/v3/` Walmart path, TLS verification, fixed `marketplace.walmartapis.com` domain, no trust of process proxies, no redirects, bounded JSON/PDF and redacted errors.
- It **rejects write operations before resolving SSM secrets**; no writes over this network path, regardless of signed permissions.
- `SZZSBJ_WALMART_CONTRACT_PUBLIC_KEYS` JSON enables v3 signature verification; `SZZSBJ_WALMART_MAX_RISK=read` keeps cloud risk ceiling read.
- Server `SZZSBJ_WALMART_SCF_PROTOCOL=3` requires matching server signing private key and public key in SCF. Leave server at protocol 1 until cloud tests pass.
- v3 accepts audited, reviewed contracts generated on the server, **not arbitrary Walmart URLs** or a blanket grant to all public API endpoints. Main server must separately authorize operations and store scope.

## Blocking prerequisites before deployment
1. Produce and verify a complete, reproducible **Python 3.10-compatible** SCF ZIP. The repository's backend `pyproject.toml` targets Python >=3.13, so copying the backend directory or using its default lockfile is **not** a verified runtime package. Validate module syntax/imports in a real Python 3.10 interpreter and pin compatible third-party wheels (notably `cryptography`, `httpx`); verify SCF handler and cold-start dependencies.
2. Inspect **all actual deployed store functions**, not just the historical eight. Legacy source lists nine store codes, including CN2603; owner must approve final exact inventory. Confirm function name, bound store, SSM role, region, and direct-public egress separately per store.
3. Review direct-public security exception against the project private-egress default. This branch honors the established **read-only** exception; it does **not** authorize WFS creation or other writes. If writes are needed, deliver a separately approved private-egress deployment with durable replay/audit and additional acceptance.
4. Package only reviewed modules needed by the cloud handler, preserve `main_handler` module path, compare dependency inventory, check compatibility with 60-second SCF timeout. Do **not** change current production `stable`, remove existing code, or modify SSM secrets to make tests pass.
5. On isolated function/test version, validate health, existing v1 inventory, signed v3 inventory, `inbound_shipments`, `inbound_shipment_items`, `inventory_log` (query pagination), rejected cross-store requests, rejected writes, expired/replayed signatures, and provider failures. Test with redacted metadata, no tokens or raw response bodies.
6. Only after one store passes, publish an immutable function version, switch that one `stable` alias under separate production authorization, then upgrade other approved stores progressively. Last, coordinate server `PROTOCOL=3` switch after cloud compatibility. Rollback: server protocol 1 and `stable` aliases to old versions.

## Test commands

```bash
cd backend
pytest -q tests/integrations/walmart/test_scf_direct_readonly.py tests/integrations/walmart/test_protocol_v3.py
ruff check app/integrations/walmart/direct_readonly_transport.py app/integrations/walmart/scf_runtime.py tests/integrations/walmart/test_scf_direct_readonly.py
ruff format --check app/integrations/walmart/direct_readonly_transport.py app/integrations/walmart/scf_runtime.py tests/integrations/walmart/test_scf_direct_readonly.py
```

This checklist does not assert a successful live rollout or blanket API readiness.

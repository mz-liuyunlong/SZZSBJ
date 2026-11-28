# System Config - WooCommerce Store Credential Management

- Status: `approved` (local acceptance only)
- Owner Approval Required: Yes for merge, migration execution, external calls, and production use
- Owner authorization evidence: the owner explicitly requested direct local code for acceptance on 2026-11-28 after the scope was described
- Base main: `5163b3876411eb279dd6b648ca3634d7f2d3b866`
- Navigation: Settings -> System Config -> Integrations -> WooCommerce
- Page key: `settings_system_config`
- Route: `/settings/system-config`

## 1. Goal

Provide a real multi-store WooCommerce credential configuration page in SZZSBJ. Store name, HTTPS origin, Consumer Key, and Consumer Secret are entered through the frontend. Credentials are encrypted on the backend, never returned to the browser, and can be tested through an explicit read-only provider request.

## 2. Scope

### In scope

- Multi-store create, list, update, enable, and disable.
- HTTPS origin normalization and server-side public-address validation.
- Fernet encryption using the existing `BUSINESS_CONFIG_ENCRYPTION_KEY` resolver.
- Super-admin-only writes and explicit connection tests.
- Credential redaction, audit events, safe error codes, and local environment isolation.
- Read-only connection test using `GET /wp-json/wc/v3/products?per_page=1&_fields=id`.
- Additive Alembic revision `20261128_0102_woocommerce_store_config`.
- System Config navigation route and Platform Integration tab.
- Local design acceptance only: ERP (Lingxing), logistics, API policy and system parameters, with browsable field details; no data, credential input, read/write APIs or fake saves. Notification rules remain in Business Config. Remove or complete preview areas before formal release.

### Explicitly not implemented

- Product creation, update, publication, deletion, or bulk listing.
- Product media upload, categories, attributes, variants, or SEO.
- Inventory, orders, shipping, refunds, analytics, or profit synchronization.
- Automatic background sync, Celery tasks, webhooks, or scheduled jobs.
- Production migration, production credentials, deployment, service restart, or real provider traffic by the assistant.

## 3. Data source and storage

- Configuration dataset: `NEW_SYSTEM_OWNED`.
- Table: `sys_woocommerce_stores`.
- Credential fields: `consumer_key_ciphertext` and `consumer_secret_ciphertext`; plaintext is accepted only in the authenticated write request and encrypted before persistence.
- Audit: reuse `biz_config_audit`; audit rows contain actor, action, and store ID only.
- External probe: one explicit GET request to the configured WooCommerce store. The response is inspected only for a valid products-list shape; no product payload or product row is persisted.
- No legacy database, RAW table, MART, or read model is used.

## 4. Permissions

- List: `require_super_admin`.
- Create, update, enable, disable, and test: `require_super_admin`.
- Frontend hides write actions unless the current user is super-admin; backend remains authoritative.

## 5. Secret and outbound safety

- Use the existing `get_business_fernet()` resolver; do not add a second encryption key.
- Never return ciphertext or plaintext credentials from read APIs.
- Blank credential fields during edit mean retain the saved value.
- Domain or credential changes invalidate the previous connection-test result.
- Enabling requires a successful test of the current saved domain and credentials.
- Super-admin manual connection tests are available in every environment. No automatic probe or sync.
- The test client requires HTTPS, rejects URL userinfo/query/fragment/path/non-443 ports and IP literals, resolves DNS, rejects any non-global address, pins the connection to a validated public IP, verifies TLS/SNI, and never follows redirects.
- The test request uses HTTP Basic Auth in the Authorization header; credentials are never placed in query parameters.
- Timeout and response-size limits are bounded. Provider response bodies and credentials are never logged or returned.
- Local, test, staging, and production encryption keys must remain separate.

## 6. API contract

- `GET /api/system-config/woocommerce/stores`
- `POST /api/system-config/woocommerce/stores`
- `PUT /api/system-config/woocommerce/stores/{store_id}`
- `POST /api/system-config/woocommerce/stores/{store_id}/test`

See `docs/api/system-config-woocommerce.md`.

## 7. Allowed local implementation files

- `frontend/src/config/navigation.ts`
- `frontend/src/router/routes.tsx`
- `frontend/src/api/woocommerceConfigApi.ts`
- `frontend/src/pages/settings/SystemConfigPage.tsx`
- `frontend/src/pages/settings/SystemConfigPage.test.tsx`
- `frontend/src/pages/settings/WooCommerceIntegrationPanel.tsx`
- `frontend/src/pages/settings/WooCommerceIntegrationPanel.test.tsx`
- `backend/app/main.py`
- `backend/alembic/env.py`
- `backend/alembic/versions/20261128_0102_woocommerce_store_config.py`
- `backend/app/modules/woocommerce_config/**`
- `backend/tests/modules/woocommerce_config/**`
- `backend/tests/db/test_alembic_scaffold.py`
- `docs/data-sources/decisions/system-config-woocommerce-credential-store-decision.md`
- `docs/api/system-config-woocommerce.md`
- `docs/sop/system-config-woocommerce.md`
- `docs/data-registry/DATA_INTERFACE_REGISTRY.md`
- `docs/frontend/PAGE_REGISTRY.md`
- `docs/BACKEND_MODULE_CATALOG.md`
- `docs/tasks/TASK_REGISTRY.md`

This is one integrated local-acceptance bundle spanning database, backend, and frontend so the owner can verify the complete local flow. It is not a single PR allowlist. Before publishing, split into database, backend, and frontend PRs according to `docs/PR_REVIEW_AND_SCOPE_GATE_RULES.md`.

## 8. Validation plan

Backend:

```bash
uv run ruff check app/modules/woocommerce_config tests/modules/woocommerce_config alembic/versions/20261128_0102_woocommerce_store_config.py
uv run pytest tests/modules/woocommerce_config tests/db/test_alembic_scaffold.py -q
uv run alembic heads
```

Frontend:

```bash
npm run test -- --run src/pages/settings/WooCommerceIntegrationPanel.test.tsx
npm run lint
npm run build
```

Local database migration is a separate owner-run step after verifying the target is the disposable/local DEV database. Do not point this migration at the read-only hybrid database or production.

## 9. Rollback

- Code rollback: revert the local patch files.
- Migration downgrade is additive but deliberately refuses to drop `sys_woocommerce_stores` while any store row exists, because rows contain encrypted credentials. Disable stores, explicitly remove local test rows through an owner-controlled process, then downgrade only if data loss is accepted.
- Production migration and rollback are not authorized by this PRP.

## 10. Acceptance

- [ ] System Config route renders and Integrations tab is selected by default.
- [ ] Multiple stores can be saved and listed.
- [ ] Consumer Key and Consumer Secret never appear in GET responses or frontend state after save.
- [ ] Editing with blank credentials retains existing credentials.
- [ ] Domain or credential changes invalidate the previous test result.
- [ ] Super-admin manual connection test uses only the bounded read-only GET probe in every environment.
- [ ] Enable is blocked until the current configuration has a successful test.
- [ ] Super-admin authorization is enforced by backend endpoints.
- [ ] WooCommerce configuration revision is 0102; owner assembles final migration chain and downgrade refuses to drop configured rows.
- [ ] Targeted tests, frontend lint/build, and local visual acceptance pass.
- [ ] No product publishing, inventory, orders, production changes, or Git publishing occurred.

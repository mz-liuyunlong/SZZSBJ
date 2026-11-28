# System Config - WooCommerce Credential Store Data Source Decision

- Investigation date: 2026-11-28
- Target page: Settings -> System Config -> Integrations -> WooCommerce
- Target API: `/api/system-config/woocommerce/stores`
- Overall status: `READY_FOR_PRP`
- Contains `NEED_OWNER_DECISION`: no
- Owner approval: approved for local implementation only by the owner's explicit 2026-11-28 instruction; merge, migration execution, provider calls, and production remain separate gates
- Related PRP: `PRPs/system-config-woocommerce-integration.md`

## 1. Source investigation

| Item | Finding |
|---|---|
| Existing page | `frontend/src/pages/settings/SystemConfigPage.tsx` did not exist on the inspected main; the navigation entry existed but routed to `ComingSoonPage` |
| Existing API | No WooCommerce configuration API was present |
| Existing storage | `biz_connectors` is constrained to `feishu_webhook` and `openai`; reusing it would alter an unrelated shared connector contract |
| Existing encryption | `backend/app/modules/business_connectors/encryption_key.py` exposes the shared Fernet resolver |
| Existing audit | `biz_config_audit` records actor, action, and object ID without storing secret values |
| Existing database | Main head is `20261127_0100_sku_ad_progress_foundation` |
| Legacy source | Not applicable; no legacy database is used |

## 2. Dataset classification

| Dataset | Authority | Classification | Strategy | Exit condition |
|---|---|---|---|---|
| WooCommerce store configuration | operations system configuration | `NEW_SYSTEM_OWNED` | Store metadata and encrypted credentials in `sys_woocommerce_stores` | Remains the configuration owner until an approved secret manager migration |
| WooCommerce connection probe | Configured WooCommerce store | External read-only verification; no business dataset retained | Explicit GET to one products-list page, inspect only response shape, do not persist response | Remove/replace only through a separately approved connector contract |
| Audit events | Existing `biz_config_audit` | `NEW_SYSTEM_OWNED` | Append actor/action/store ID only | Existing audit retention policy |

## 3. Data lineage

| Field | Source | Target | Transformation | Sensitivity |
|---|---|---|---|---|
| `name` | Super-admin input | `sys_woocommerce_stores.name` | Trim and length validation | Internal configuration |
| `store_url` | Super-admin input | `sys_woocommerce_stores.store_url` | Normalize HTTPS origin; reject path/query/userinfo/non-443 port/IP literal | Internal configuration |
| `consumer_key` | Super-admin input | `consumer_key_ciphertext` | Fernet encryption before persistence | Secret |
| `consumer_secret` | Super-admin input | `consumer_secret_ciphertext` | Fernet encryption before persistence | Secret |
| connection result | Explicit test action | `last_test_*` | Safe code and timestamp only | Operational metadata |

## 4. Safety and permissions

- Read: `require_super_admin`; response exposes configured booleans only.
- Write/test: `require_super_admin`.
- Secret owner: the system owner / authorized super-admin.
- Secret reference: `woocommerce_store:{store_id}:consumer_key` and `woocommerce_store:{store_id}:consumer_secret` (encrypted database fields; never place values in documentation).
- Rotation: create replacement WooCommerce REST API credentials, update both values through the page, retest, then revoke the previous key in WordPress.
- Revocation: disable the store in the operations system and revoke the corresponding REST API key in WooCommerce.
- Exposure response: disable the store, revoke the exposed key pair in WooCommerce, rotate credentials, review audit events, and retest.
- No automatic provider call on page load, save, list, or enable.
- The explicit manual probe is available to super admins in every environment. It blocks private/non-global DNS targets and redirects.

## 5. Final decision

- Recommended strategy: `NEW_SYSTEM_OWNED` for store configuration; explicit bounded external read-only probe for credential verification.
- Legacy database: not used.
- RAW/ODS/MART: not applicable; no product payload is retained.
- Provider business sync: explicitly out of scope.
- Production calls, migration, deployment, and credential entry remain separate owner actions.

# System Config - WooCommerce API

Base path: `/api/system-config/woocommerce/stores`

All endpoints use the standard system success/error envelope and authenticated backend session.

## Permissions

- `GET`: super-admin only.
- `POST`, `PUT`, and `/test`: super-admin only.
- Plaintext credentials and ciphertext are never returned by any response.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | List configured stores; returns configured booleans only |
| POST | `/` | Create a disabled store configuration |
| PUT | `/{store_id}` | Update name/domain/credentials or enable/disable |
| POST | `/{store_id}/test` | Explicit read-only connection probe |

## Create request

```json
{
  "name": "RINIMA",
  "store_url": "https://www.example.com",
  "consumer_key": "<entered-by-owner>",
  "consumer_secret": "<entered-by-owner>",
  "enabled": false
}
```

Create requires both credentials and always starts disabled. `enabled=true` is rejected until a successful test exists for the saved configuration.

## Update request

```json
{
  "name": "RINIMA",
  "store_url": "https://www.example.com",
  "enabled": false
}
```

`consumer_key` and `consumer_secret` are optional during update. Omitted or blank values preserve the encrypted saved values only when the domain is unchanged. A domain change requires both credentials to be entered again. Changing the domain or either credential invalidates the prior test result and forces the store disabled until retested.

## List response data

Each store contains:

- `id`, `name`, `store_url`, `enabled`
- `consumer_key_configured`, `consumer_secret_configured`
- `last_test_at`, `last_test_ok`, `last_test_code`, `updated_at`

No secret, ciphertext, authorization header, or provider response body is returned.

## Test behavior

`POST /{store_id}/test` is available to super admins in every environment. It runs only on an explicit authenticated request; no automatic tests are triggered. A successful test confirms read access only.

The backend sends one bounded HTTPS Basic Auth GET request to:

`/wp-json/wc/v3/products?per_page=1&_fields=id`

The response is not stored. Only a safe result code and timestamp are recorded. Redirects are not followed.

Possible result codes include `OK`, `WOO_DNS_FAILED`, `WOO_HOST_NOT_PUBLIC`, `WOO_CONNECTION_FAILED`, `WOO_AUTH_FAILED`, `WOO_PERMISSION_DENIED`, `WOO_API_NOT_FOUND`, `WOO_REDIRECT_BLOCKED`, `WOO_RATE_LIMITED`, `WOO_UPSTREAM_ERROR`, and `WOO_RESPONSE_INVALID`.

## Security

- HTTPS origin only; no URL credentials, path, query, fragment, non-443 port, or IP literal.
- DNS results must all be public global addresses; the TCP connection is pinned to a validated address and TLS hostname verification remains enabled.
- No redirect, proxy environment, credential query parameter, or response-body logging.
- Fernet encryption reuses `BUSINESS_CONFIG_ENCRYPTION_KEY` / `BUSINESS_CONFIG_ENCRYPTION_KEY_FILE` through the existing resolver.

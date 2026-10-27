# Decodo and other business integrations: one protected encryption key

Decodo previously required its own `DECODO_CONFIG_ENCRYPTION_KEY`, causing
`PUT /api/business-rules/decodo` to return 503
`DECODO_ENCRYPTION_KEY_NOT_CONFIGURED` even when the business connector secret
store was configured.

Decodo now uses the existing centrally managed business Fernet key if a dedicated
Decodo key is not set:

- `DECODO_CONFIG_ENCRYPTION_KEY` (legacy): **wins when present** to preserve old Decodo ciphertext.
- `BUSINESS_CONFIG_ENCRYPTION_KEY` or `BUSINESS_CONFIG_ENCRYPTION_KEY_FILE`:
  existing secure shared resolver; choose exactly one.
- If no usable key exists, the system **fails closed** with a safe 503 code.
  It does not generate ephemeral keys or persist credentials in plain text.

An existing Decodo ciphertext encrypted with a legacy key cannot be decrypted
with a different shared key. Do not silently delete the old key, replace its
ciphertext, or switch source before separately reviewing a migration.

## Production readiness

1. Confirm an original, stable business connector key has been provisioned to
   the actual Backend process. Merging code **cannot** create secret material.
2. If legacy Decodo credentials already exist, retain their original key.
   The absence of a legacy key in a running process does not prove no old ciphertext
   exists in the database.
3. Use `python -m app.modules.business_connectors.preflight_encryption`
   to validate the shared key without printing credentials.
4. Deploy through the approved release procedure; verify a newly configured
   Decodo credential saves and can be read in a safe authorized integration test.
   Avoid paid scrape requests without explicit approval.

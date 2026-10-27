# Business connector encryption: production preflight

The POST /api/business-rules/connectors endpoint encrypts API credentials using one stable Fernet key. If BUSINESS_CONFIG_ENCRYPTION_KEY is unset/invalid, the API returns 503 with error.code BUSINESS_ENCRYPTION_KEY_MISSING. This is a server configuration incident, not an OpenAI availability error.

Supported secret sources (exactly one):
- BUSINESS_CONFIG_ENCRYPTION_KEY: existing injected Fernet key (preserved for backward compatibility).
- BUSINESS_CONFIG_ENCRYPTION_KEY_FILE: absolute path to a protected file containing the same Fernet key. The file must have no group/other permission bits (e.g. 0600) and be readable by the backend process. Never commit this file.

Production operator steps:
1. Identify the **existing** original key from the approved secret manager/configuration. If encrypted connector rows already exist, do not create or swap to a new key.
2. Verify the key is available to the actual Backend, Celery Worker and Beat runtime identities; avoid exposing the secret with systemctl show Environment or stdout.
3. Before restarting, use the backend virtualenv and the approved environment to run:
   `python -m app.modules.business_connectors.preflight_encryption`
   This prints only one safe status code, never the key.
4. After independently approved deployment/restart, test the authorized connector save and read-back. The public API never returns raw credentials.
5. If the key is lost and encrypted records exist, stop and escalate; do not silently rotate, delete ciphertext or generate replacement credentials.

This repository intentionally does **not** generate a new key during boot or on requests. The project owner must provision the key securely. Neither merging this PR nor CI can inject secrets into production.

Known incident: Authorization bearer and session cookie values were inadvertently shared while troubleshooting. Revoke impacted sessions and check legacy cookie validity separately; do not paste headers or log secret values.

# SOP - Configure a WooCommerce Store

## 1. Prepare the WooCommerce REST API key

In the WordPress store admin, open WooCommerce -> Settings -> Advanced -> REST API. Create a key for the intended store owner with Read/Write permission. Keep the Consumer Key and Consumer Secret in a secure password manager.

## 2. Add the store in the operations system

Open Settings -> System Config -> Integrations -> WooCommerce.

1. Select Add Store.
2. Enter a recognizable store name.
3. Enter the HTTPS site origin only, for example `https://www.example.com`.
4. Enter Consumer Key and Consumer Secret.
5. Save. The store remains disabled.

The domain must not contain `/wp-admin`, `/wp-json`, another path, query parameters, or credentials.

## 3. Test the connection

Super admins can click Test Connection in any environment. A successful test verifies read access, not write access. Confirm that the local environment uses its own `BUSINESS_CONFIG_ENCRYPTION_KEY`; never reuse the production key in DEV.

Select Test Connection. The backend performs a read-only products-list request limited to one item ID. It does not create or update products. Review the safe result code shown by the page.

## 4. Enable the store

After a successful test, enable the store using the status switch. The backend rejects enablement if the saved domain or credentials have not passed a successful test.

## 5. Rotate or revoke credentials

To rotate, edit the store and enter the new Consumer Key and/or Consumer Secret. Leave both fields blank to retain the existing values. Any credential or domain change clears the previous test result and disables the store until retested.

To revoke, disable the store in the operations system and revoke the corresponding REST API key in WordPress.

## 6. Security rules

- Never paste credentials into chat, tickets, source files, logs, or screenshots.
- The UI never displays saved secret values.
- Only super-admins can create, edit, test, enable, or disable stores.
- A failed or untested store cannot be enabled.
- This first phase does not publish products or synchronize inventory, orders, or refunds.

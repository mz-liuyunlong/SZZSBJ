# Findings

- `mart_listing_management_current` already has the required stable unique key and approved descriptive fields.
- `category` is the product-source category; page-observed Walmart category remains a separate RAW field.
- `wfs_available_quantity` is nullable and must stay nullable in the contract.
- Existing user data-scope resolution rejects non-user machine principals, so the service endpoint needs a dedicated exact-path all-current scope documented in the PRP.
- The monitor client already supports bearer auth, nested `data.items`, pagination and nullable inventory after the companion local change.
- The generic `/api/integrations/**` permission rule would otherwise remap the dedicated machine permission, so the exact GET policy must be registered first.
- No schema change is required: the approved fields all exist on the current Listing MART.

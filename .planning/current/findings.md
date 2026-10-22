# Findings

- The monitor producer emits one `walmart-monitor.raw.v1` event containing targets, all provider attempts, compressed source artifacts, and a final observation.
- Chrome and Decodo are attempts within one event, not separate RAW schemas.
- The receiver needs a dedicated append-only L2 RAW table because the event includes replay evidence and compressed artifacts not represented by current Lingxing request-reference tables.
- Current project authentication resolves bearer sessions through IAM; the approved service token therefore needs an exact-route, least-privilege principal before IAM resolution.
- Current Alembic head at approval time is `20261020_0047_walmart_order_identity_guard`; the new additive revision is `0048`.

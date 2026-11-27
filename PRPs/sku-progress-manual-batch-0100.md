# SKU progress manual/batch continuation candidate

Source decision: `docs/data-sources/decisions/sku-progress-manual-0100-decision.md`. Based on 28-file hash-verified local snapshot, HEAD 258fffd95d78aeea9a8c97dbb23788417c758ab9; main independently checked at ae4a8cb8fb84ff3cb9f11c39a76c4adb3268a068. Existing 0100 schema only. No CSS, column definitions, existing purchase provider or migrations changed.

Manual state: reuse current dialog; prefill reason, note and status, state changes through note editor only; require note, reason for pause/termination. Store manual override and event atomically; version conflict refuses lost update. Current account scope, existing tracking auth policy, deny preview and split-source writes. No automatic completion or reopen terminal states; these require explicit decisions. On success invalidate only SKU progress queries.

Batch purchase: selection once per SKU on current page, select one eligible listing/store per SKU, fixed 20. Reuse single POST with existing permissions, all gates and durable claim; sequential per SKU results, no automatic retry; uncertain result needs manual reconciliation. Do not continue queuing requests after dialog unmount. No change to direct purchase authorization or real transport activation. Cross-workflow old/new approval race remains unresolved; must not activate in production before verification.

Tests: isolated mocked Python service + existing purchase tests; isolated TS adapter type checks and TSX syntax. Complete frontend build, real PostgreSQL integration, actual permission mapping, E2E/CI and source registry review remain pending. Installation candidate with exact original file hashes and backup. No Git operation, external calls, migration, or data mutation performed by installer.

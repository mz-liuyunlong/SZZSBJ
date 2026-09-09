# Component Reuse Examples

These are decision examples, not proof that a feature or page is implemented.

| Scenario | Decision | Reason |
|---|---|---|
| New report needs fixed header and pagination | Reuse `ReportTableShell` | Existing shared pattern owns scroll/density/pagination |
| New report needs SKU search | Reuse or extend `ConnectedSearch`/`SkuSearchInput` after catalog and file check | Do not create another toolbar |
| One page has a unique simple detail panel | Page Local | No second consumer |
| Two pages need identical status rendering | Reuse existing status/cell renderer or propose Shared | One meaning and token mapping |
| Existing Shared covers most needs but lacks one optional action | Extend after compatibility review | Smaller contract than a parallel component |
| Shared extension would change all consumers | Stop and request design decision | Cross-page product impact |

Each frontend implementation prompt must include the table from `docs/ai-prompts/FRONTEND_IMPLEMENTATION_PROMPT.md` with evidence-based decisions.

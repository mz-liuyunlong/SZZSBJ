# Page Layout Patterns

## Standard Patterns

| Page type | Required foundation | Typical structure |
|---|---|---|
| Standard business page | `PageShell` | title/help -> filters/actions -> content states |
| High-density report | `PageShell` + `ReportTableShell` | connected filters -> table internal scroll -> fixed pagination |
| Detail workflow | `PageShell` + Ant Design Modal/Drawer | summary -> grouped details/actions |
| Planned/no-API page | `PageShell` or approved page shell | honest no-api/empty state; no fake rows |
| Error state | existing error boundary/pages | safe message -> recovery action -> request ID when available |

## Required Rules

- MainLayout owns global navigation, breadcrumb/tab shell and viewport containment; pages do not duplicate them.
- Page content must not cause window/body horizontal scrolling; dense tables may scroll internally.
- Filters, actions, loading, empty, error, permission and stale/partial states have one clear location.
- Use existing Ant Design/ProComponents behavior before custom table, pagination, modal or form infrastructure.
- Mobile/narrow layouts preserve task completion, focus order and dialog usability.
- A new layout pattern requires design-system review; page-local styling cannot silently become a pattern.

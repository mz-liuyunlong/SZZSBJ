# Component Usage Guide

## Decision Order

1. Verify catalog status and actual file.
2. Reuse stable Shared component.
3. Extend it if the existing contract covers at least 70% without breaking consumers.
4. Use Page Local for single-page, simple behavior.
5. Propose a new Shared component only with two real consumers or a clear cross-page contract.

## Preferred Components

| Need | Preferred source |
|---|---|
| Page title/status/help | `PageShell` |
| High-density table/pagination/scroll | `ReportTableShell` |
| Connected query entry | `ConnectedSearch` |
| Reset action | `ResetButton` |
| Runtime column settings | `RuntimeColumnConfigDrawer` |
| Resizable title | `ResizableColumnTitle` |
| Common report cells | `ReportTableCells` exports |
| Form/modal/drawer/button | Ant Design |

## Extension Rules

- Preserve public props and accessibility unless migration is approved.
- Avoid boolean-prop growth; if consumers need conflicting behavior, re-evaluate the abstraction.
- Tests cover both existing consumers and new behavior.
- New/changed Shared components update the catalog with status, owner, consumers, props stability and token compliance.

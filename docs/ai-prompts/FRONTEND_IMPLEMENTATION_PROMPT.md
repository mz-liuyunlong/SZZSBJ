# Frontend Implementation Prompt

```text
Role: Frontend Engineer
Worktree: <absolute path>
Branch: <branch>
Approved PRP/Page Spec: <paths>
Allowed files: <exact list>

Preflight pwd/branch/clean status/base and stop on mismatch. Read project entry rules and Approved PRP.

Step 1 — Component inventory check:
- Read docs/UI_COMPONENT_CATALOG.md.
- Inspect relevant frontend/src/components/** files.

Step 2 — Design system check:
- Read docs/design-system/DESIGN_TOKENS.md.
- Read docs/design-system/PAGE_LAYOUT_PATTERNS.md.
- Confirm typography, spacing, color, radius, status colors and table density.

Step 3 — Component Reuse Plan:
- Output the plan below before implementation.
- Reuse stable Shared components; extend when they safely cover at least 70%; use Page Local for one-page needs.
- Stop if uncertainty affects Shared contracts or design consistency.

## Component Reuse Plan

### Page Type
- Detected page type:
- Reason:

### Reuse Decisions

| UI Area | AI Decision | Existing Component | Reuse / Extend / New / Page Local | Reason | Catalog Update Required |
|---|---|---|---|---|---|
| Page shell |  |  |  |  |  |
| Header |  |  |  |  |  |
| Search/filter |  |  |  |  |  |
| Table shell |  |  |  |  |  |
| Cell renderers |  |  |  |  |  |
| Status display |  |  |  |  |  |
| Empty/error state |  |  |  |  |  |
| Actions/buttons |  |  |  |  |  |
| Modal/drawer |  |  |  |  |  |

### Existing Components Reused
-

### New Components Proposed
-

### Components Not Reused
- Component:
- Reason:

### Design Token Check
- Colors:
- Font:
- Font size:
- Spacing:
- Border radius:
- Table density:
- Status colors:

### Risks / Uncertainty
-

Implement only after the plan is consistent with the PRP. Frontend calls only approved FastAPI contracts; no external API, secret, authoritative calculation or mock disguised as real data. Do not alter navigation without owner approval. Update Page/Data Interface/Component registries when triggered.

Run existing lint/type/test/build and required visual/E2E checks. Report factual results, scope and Explicitly not implemented. Do not perform Git write/upload actions.
```

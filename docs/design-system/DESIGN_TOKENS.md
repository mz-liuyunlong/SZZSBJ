# Design Tokens

Status: `draft; approved only after owner review and merge`

## Source of Truth

Ant Design theme tokens and the single application theme configuration are the visual source of truth. This document defines semantic usage, not a second hardcoded palette.

| Area | Required token source | Rule |
|---|---|---|
| Color | Ant semantic color tokens | No page-local brand/status hex values |
| Typography | global font family and typography tokens | No page-local font stack |
| Font size/line height | typography scale tokens | Use semantic hierarchy, not arbitrary values |
| Spacing | spacing tokens / documented layout variables | Reuse the smallest existing scale value |
| Radius | border radius tokens | No new radius language per page |
| Shadow | elevation/shadow tokens | Use only for established overlay/card patterns |
| Status | success/warning/error/info/default tokens | Meaning must stay consistent |
| Table density | shared report/table shell settings | No per-page density system |

## Required Rules

- Component CSS may define local layout variables only when no semantic token exists; name and reason must be documented.
- Brand changes update the centralized theme/token decision, not every page.
- Accessibility contrast, focus visibility, reduced motion, touch targets and narrow-screen behavior cannot be removed for visual similarity.
- New token categories require owner/design-system approval and a catalog update.

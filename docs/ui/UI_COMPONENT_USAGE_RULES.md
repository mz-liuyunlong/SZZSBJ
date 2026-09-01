# UI Component Usage Rules

This file defines how frontend pages use the approved UI component system.

## 1. Approved UI component system

1. Frontend pages must use `Ant Design + ProComponents` as the approved admin UI component system.
2. Basic layout, menus, buttons, modals, drawers, tabs, breadcrumb, cards, alerts, tags, badges, empty states, and loading states must use Ant Design components first.
3. Admin table pages must use `ProTable` first.
4. Admin form pages must use `ProForm` first.
5. Data cards and metric cards should use `Card`, `Statistic`, or `ProCard`.
6. Charts use ECharts.
7. Icons use `@ant-design/icons`.

## 2. Forbidden UI implementation

1. Do not hand-code complex admin tables, forms, filters, pagination, modals, drawers, cards, tabbars, breadcrumbs, or status displays with raw HTML and custom CSS.
2. Do not create a different table, form, modal, status, filter, pagination, or card style for each page.
3. Do not introduce a second UI component library.
4. Do not install another UI framework, table library, form library, icon library, or admin template for one page.
5. Do not copy external admin template code into the project.

## 3. Shared component layer

Shared components should use semantic names based on responsibility, for example:

```text
frontend/src/components/common/DataTable/
frontend/src/components/common/DataForm/
frontend/src/components/common/StatusTag/
frontend/src/components/common/MoneyText/
frontend/src/components/common/PercentText/
frontend/src/components/common/NumberText/
frontend/src/components/common/DateTimeText/
frontend/src/components/common/MetricCard/
frontend/src/components/common/ConfirmAction/
frontend/src/components/common/EmptyState/
frontend/src/components/common/ErrorState/
frontend/src/components/common/LoadingState/
frontend/src/components/common/NoPermissionState/
```

Rules:

1. Shared components must be placed under `frontend/src/components/`.
2. Feature-only components may live inside the feature module.
3. Page-local components must stay small and must not duplicate shared components.
4. Custom components must wrap or compose the approved UI component system unless there is a documented reason.

## 4. Data display components

1. Money values must use a shared money display component.
2. Percent values must use a shared percent display component.
3. Date and time values must use a shared date/time display component.
4. Status values must use a shared status component.
5. Empty values must not display `NaN`, `undefined`, `null`, or raw empty strings.

## 5. Ready gate

A page cannot be marked `ready` if it:

1. bypasses the approved UI component system,
2. hand-codes complex admin UI with raw HTML/CSS,
3. lacks loading, empty, error, or no-permission states,
4. uses inconsistent table, form, status, or filter styles,
5. lacks layout acceptance coverage when required.

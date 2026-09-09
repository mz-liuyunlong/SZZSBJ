# Design System and Component Reuse Rules

## Purpose

前端 AI 在既定设计系统、组件库、页面模板、数据和导航边界内实现，不自由发明页面体系。

## Required Preflight

写新页面前必须读取：

- `docs/UI_COMPONENT_CATALOG.md`。
- `docs/design-system/DESIGN_TOKENS.md`。
- `docs/design-system/PAGE_LAYOUT_PATTERNS.md`。
- `docs/design-system/COMPONENT_USAGE_GUIDE.md`。
- 相关 `frontend/src/components/**` 实际文件。

## Component Reuse Decision Rule

1. 已有 Shared 组件覆盖该 UI 区域时必须复用。
2. 已覆盖 70% 以上需求时优先扩展，不另建。
3. 只在当前页面使用的简单能力可为 Page Local。
4. 两个以上页面会使用时必须评估 Shared。
5. 新增 Shared 组件必须同 PR 更新 UI Component Catalog。
6. 不确定复用是否安全且会影响 Shared/设计一致性时停止确认。
7. 不得因图省事新造视觉样式。

前端 AI 必须自己完成组件盘点并输出 `Component Reuse Plan`，不得把“用哪个组件、是否复用表格/搜索栏”丢给负责人。只有组件冲突、复用会破坏既有契约、设计系统缺少模式或涉及产品决定时才询问。

## Visual Rules

- 颜色、字体、字号、间距、圆角、阴影、表格密度和状态色来自 Ant Design theme token 或本项目 design token。
- Ant Design 主题集中配置；页面不得随意覆盖或引入第二套主题。
- 既有硬编码是 touched-file 改善对象，不授权一次性全项目重构。
- 重复造 Shared 组件、硬编码主题、缺失 reuse plan 或 catalog 更新可直接拒绝 PR。

# PR Review and Scope Gate Rules

## Purpose

保证 PR 单一、可验证、可回滚，阻止跨范围“顺手修改”。

## Scope Rules

- 一个 PR 只完成一个明确任务和一个主要领域。
- docs-only PR 不得改代码；frontend PR 不得改 backend；backend PR 不得改 frontend；database PR 不得混入业务页面。
- 最终 diff 必须与已批准 allowlist 完全一致，发现越权文件立即停止。
- 超过 20 个文件或跨 3 个以上领域，PRP/PR 必须说明无法安全拆分的原因和原子回滚边界，否则拆分。
- 本规则基线 PR 是一次性例外：入口、规则、registry 和 prompt 模板必须同 PR 避免死链接；不授权后续超级 PR。
- 每个 PR 必须列出 `Explicitly not implemented`、验证证据、风险和回滚方式。

## Frontend Rejection Conditions

Frontend PR 可因以下任一项拒绝：

- 重复创建已有 Shared 组件。
- 页面自行硬编码颜色、字体、字号或另一套主题。
- 未检查组件清单就新建表格、搜索栏、状态标签或金额展示组件。
- 修改视觉体系却不更新设计规则。
- 新增 Shared 组件但未更新 `docs/UI_COMPONENT_CATALOG.md`。
- 缺少 `Component Reuse Plan`。

## Review Checklist

- [ ] 分支、base、工作区和任务一致。
- [ ] 文件范围、依赖、数据源、权限和安全边界一致。
- [ ] 测试结果真实且失败未隐藏。
- [ ] Registry/catalog/page/task 文档按触发规则更新。
- [ ] 没有 secret、mock 冒充真实数据或 future scope 实现。
- [ ] 回滚不会破坏其他任务。

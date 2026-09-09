# UI Copy and Status Text Rules

## Required Rules

- 文案说明用户当前状态、影响和下一步；避免内部术语、模糊“失败了”或虚假成功。
- `planned/no_api/mock_only/display_only` 必须使用诚实提示，不能伪装已连接或已保存。
- Loading、empty、error、permission denied、stale、partial success、sync states 使用统一词义。
- 删除、覆盖、导出、同步、重算等高风险动作明确对象、范围和不可逆影响。
- Error 文案遵守安全消息规则，不暴露内部实现或 secret。
- 状态名称来自 canonical contract；不得只在页面新增同义状态。
- 中文主文案简洁一致；可访问名称不得只依赖图标、颜色或 tooltip。

跨页面状态文案变化需要 owner/设计系统确认并更新使用方。

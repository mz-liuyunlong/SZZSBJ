# Release and Feature Flag Rules

## Required Rules

- Merge、deploy、enable 和 business release 是不同状态与授权。
- Feature flag 必须有 owner、purpose、environment、default、audience/data scope、start/end、rollback 和 removal task。
- 安全、权限、数据质量或 migration 门禁不得被 flag 绕过。
- 默认关闭真实外部写入、通知、同步、AI 自动动作和高风险功能，直到明确批准。
- 前后端 flag contract 必须一致；前端隐藏不替代后端阻断。
- 发布前确认 CI、migration compatibility、配置、监控、数据 freshness、回滚和人工验收。
- Flag 不得永久替代代码/状态模型；稳定后独立任务移除旧路径。

生产启用、回滚和部署由负责人控制，AI 不自动执行。

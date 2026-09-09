# Temporary Code and TODO Rules

## Required Rules

- 临时代码必须有明确状态：`mock_only`、`no_api`、`display_only`、feature flag 或测试 fixture。
- TODO 必须写 owner、原因、退出条件和关联 task/PRP；无追踪信息的 TODO 不得合并。
- 临时 fallback 不得绕过权限、数据质量、错误处理或 Source Decision。
- mock 不得伪装真实数据，不得进入生产权威结果。
- debug log、临时开关、注释掉的实现、一次性脚本和本地文件在合并前删除或取得明确保留批准。
- 临时代码到期后通过独立任务移除，不在无关 PR 顺手清理。

## Forbidden Patterns

永久 `temporary`, 静默 fallback, hardcoded production data, 注释掉大段代码, 未登记的 feature flag。

# Incident and Rollback Rules

## Required Rules

- 每个实现 PR 说明回滚边界、触发条件、owner、验证和不可逆数据影响。
- 事故处理中先停止扩大影响、保留证据、记录时间线和 request/run/deploy ID，再执行负责人批准的恢复步骤。
- 代码优先用可审查 revert；数据库、migration、数据回填、规则重算和外部写入不得自动回滚。
- 禁止删除日志、RAW、audit 或失败记录来“恢复正常”。
- Secret 暴露时不回显值，立即停用/轮换并评估 Git/history/log 影响。
- 事故复盘区分根因、触发、检测、影响、缓解、修复和预防任务。

## Stop Conditions

恢复动作可能写生产、丢数据、扩大权限或不可逆时，等待负责人及对应运维/数据库批准。

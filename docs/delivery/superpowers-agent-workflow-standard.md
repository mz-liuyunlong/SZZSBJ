# Superpowers Agent Workflow Standard — Project Rule Pack V1.0

## 1. Positioning

Superpowers 是可选 AI 编程流程插件，用于需求澄清、计划拆分、TDD、代码评审和收尾验收。

它不是 本项目 生产依赖，也不是项目最高规则。

## 2. Allowed use

```text
需求澄清
设计讨论
任务拆分
TDD 思路
代码评审
分支收尾
```

## 3. Forbidden

```text
覆盖 Project Rule Pack 规则
修改 old-system
连接生产数据库
运行同步任务
重启服务
自动部署
绕过 PRP 确认
绕过 CI / Playwright / pytest
长时间无人看管执行高危任务
```

## 4. Worktree rule

如使用 git worktree，只能在新系统仓库内为 feature 分支创建隔离工作区。不得对 `old-system/` 或生产环境执行写操作。

## 5. Completion rule

即使使用 Superpowers，完成报告仍必须采用 Project Rule Pack 格式。

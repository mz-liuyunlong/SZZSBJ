# Owner Approval and Escalation Rules

## Purpose

明确 AI 建议、架构批准与负责人授权之间的边界。

## Owner Approval Required

- PRP 从 Draft 进入 Approved，及每次单独实现 Prompt。
- 新增/删除/重命名导航或核心业务字段。
- 数据真源、技术栈、权限模型和生产上线决定。
- 真实数据库、服务器、外部 API、密钥、migration、回填或同步。
- 财务、利润、费用、佣金、库存、广告、结算、退款口径。
- CI、部署、生产配置、依赖或锁文件变更。
- 删除旧代码、旧字段、旧文档或不可逆操作。

## Escalation Format

AI 必须报告：当前事实、阻塞点、涉及范围、风险、最小可选方案、推荐方案、需要负责人回答的精确问题。不得把默认选项当批准。

## Approval Semantics

- 批准只对写明的任务、文件、环境、命令和期限有效。
- Read approval 不包含 write；PRP approval 不包含自动实现；staging approval 不包含 push/merge。
- 负责人本人执行最终 git add、commit、push、PR、merge 和分支/worktree 删除。

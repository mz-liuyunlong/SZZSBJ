# Secret and Environment Rules

## Required Rules

- 真实 Token、密码、Webhook、Cookie、Authorization header、数据库连接串和私钥不得进入 GitHub、日志、PR、文档、测试、RAW、截图或聊天。
- 文档和 registry 只记录 `secret_ref`；`.env.example` 只放变量名与不可用 placeholder。
- 真实 `.env` 不得提交；前端永远不得接收服务端或外部平台 secret。
- AI 不得要求用户把密钥粘贴进聊天；负责人只在受控本地/部署环境输入。
- 日志和错误必须脱敏，不得输出完整 URL、header、payload 或凭据片段。
- `local/dev/test/staging/production` 配置隔离，低环境不得复用 production credential。
- 本地和测试默认 fail closed，不得因缺配置误连生产。
- 生产 secret 只由部署环境或批准的 secret manager 注入。
- 每个新增外部连接必须在 PRP 说明 secret owner、secret_ref、轮换、撤销、审计和暴露响应。

## Stop Conditions

发现疑似 secret 时停止，不回显具体值；报告文件/行号与风险类型，并由负责人轮换和清理历史。

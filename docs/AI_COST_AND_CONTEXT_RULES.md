# AI Cost and Context Rules

## Required Rules

- AI 任务声明 purpose、允许输入、模型白名单、预算/调用上限、owner 和保留策略。
- 只提供完成任务所需最小上下文；不得把整个仓库、RAW、secret 或越权字段发送给模型。
- 长任务使用仓库/本地计划和 handoff 重建上下文，不依赖聊天记忆或重复粘贴敏感资料。
- 记录 model/version、prompt version、token/费用、request/run ID、input reference、citation 和 review status。
- Cost limit 达到时 fail closed，不静默切换更贵模型或扩大上下文。
- Cache/retrieval 必须遵守 ACL、数据新鲜度、删除传播和来源引用。
- AI 输出是 candidate，人工 Review 前不得触发权威写入或高风险动作。

真实 AI use case 需独立 PRP，不因本规则获得 API 或密钥权限。

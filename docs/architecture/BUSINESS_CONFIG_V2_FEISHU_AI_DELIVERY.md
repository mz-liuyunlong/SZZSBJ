# 业务配置 V2 · 飞书群与 OpenAI 接入验收

## 范围和部署边界

- 所有源码仅在功能分支和 Draft PR 中提交，严禁自动运行生产迁移或发送消息。
- 新增 `backend/alembic/versions/20261025_0059_business_connector_control.py` 只定义数据表；迁移需要独立批准，禁止通过页面、测试或部署自动执行。
- 现有 Decodo、飞书员工通讯录和飞书应用机器人继续保持既有接口。
- 正式的飞书群通过官方自定义群机器人 Webhook 接入，凭据与 URL 均使用 Fernet 加密存储。
- OpenAI 是首个模型 Adapter，业务层统一调用 `backend/app/integrations/llm/openai_provider.py`，不在前端直接请求模型接口。
- 旧版其他集成草稿仍保留在浏览器会话，仅作界面规划；与真实连接分离，严禁把密钥填入草稿。

## 安全配置（仅由受控运行环境设置）

| 变量 | 含义 | 缺省状态 |
|---|---|---|
| `BUSINESS_CONFIG_ENCRYPTION_KEY` | 合规的 Fernet 加密密钥 | 不配置时保存凭据失败关闭 |
| `BUSINESS_NOTIFICATIONS_OUTBOUND_ENABLED` | 允许 Celery / 显式派发飞书消息 | false，不发送 |
| `BUSINESS_CONNECTOR_TEST_CALLS_ENABLED` | 允许管理员执行对外连接测试 | false，拒绝测试 |
| `CELERY_BROKER_URL` | Celery Broker，沿用原有配置 | 生产必须单独配置 |
| `PRODUCTION_MIGRATIONS_AUTHORIZED` | 由运维授权的既有生产迁移保护 | false |

环境隔离：local、dev、test、staging、production 使用不同的密钥和飞书群；严禁拿生产凭据用于低环境。原有 Celery Beat 每 60 秒安排一次通知 Tick，通知使用独立的 `notifications` 队列，生产 Worker 需要明确订阅该队列。在环境开关关闭时 Tick 不访问外部服务。

## 操作步骤

1. 在授权的非生产数据库上执行经代码审查的 Alembic 迁移；核对唯一 Head 及回滚预案。
2. 确认超级管理员权限，通过业务配置 V2 → 正式服务连接管理创建群机器人。粘贴官方 `https://open.feishu.cn/open-apis/bot/v2/hook/...` URL 和可选签名密钥，初始保持停用。
3. 设置消息事件 → 飞书群、冷却时间和日上限。建议先创建通知模板。
4. 单独启用该连接、该路由，且经授权部署环境配置外发开关，才允许工作任务发送。
5. 测试连接需要二次确认并单独开启测试开关。发送的测试消息固定为业务配置中心的测试提示，不引用用户敏感数据。
6. 在发送记录查看状态、次数和安全错误码；最多三次尝试，退避重试，不自动改业务事务状态。
7. 创建 OpenAI 连接时，只能使用服务端加密 API Key；配置默认模型、备用模型、白名单、每日额度、月预算，以及经人工核准的每百万输入/输出 Token 单价。
8. AI 模型生成必须由超级管理员显式调用；请求先在数据库预留最大估算成本并做日/月预算检查，模型返回后记录消耗 Token 和估算成本。最终账单应以服务商为准。
9. 不要在界面、聊天、CI 或日志中保存或展示完整密钥、Webhook URL、Token、AI 提示词内容或外部响应正文。

## 权限和 API

- 配置读取：现有 `business-rules:read` 权限；所有 Secret 字段不可从 API 返回，连密文也不返回。
- 配置写入、路由、模板、测试、消息派发、AI 调用：现有后端 `require_super_admin` 严格检查。
- 基础接口前缀：`/api/business-rules/connectors`。
- 群路由：`GET /routes/list`、`POST /routes`。
- 模板：`GET /templates/list`、`POST /templates`。
- 投递记录：`GET /deliveries/list`、`GET /usage/summary`；审计为 `GET /audit/list`。
- 消息队列：`POST /notifications/queue`；显式派发：`POST /notifications/dispatch`。
- AI 调用：`POST /ai/generate`。连接检查：`POST /{connector_id}/test`。

## 待人工验收 / 不可自动跨越的边界

- 实际供应商 Secret、OpenAI 价格和模型可用性由管理员在受控环境核准，不预置真实密钥或供应商数据。
- 自动业务事件来源目前需由各模块在业务事务提交成功之后调用队列入口。不能假设创建了通知路由就自动覆盖库存、广告、审批和同步模块的所有事件。
- 计费为人工设置单价的保守估算；不能视为供应商最终账单。价格变更需要重新核准。
- 新增数据表、Celery Worker、实际飞书群外发、AI 模型调用均需部署和运维单独审批。
- 必须完成 CI、前端构建、非生产迁移与 API 联测、密钥安全及重试幂等验收，才能将 Draft PR 标记为 Ready。

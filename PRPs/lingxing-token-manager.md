# Lingxing Token Manager PRP

Status: `Approved`

Owner Approval Required: `Completed for Token Manager implementation gate.`

Implementation Allowed: `Yes, but only for Lingxing Token Manager backend implementation, and only after the owner issues a separate backend implementation prompt.`

Main Execution Role After Approval: `Backend Engineer`

## 1. Goal

为后端规划最小 Lingxing Token Manager：按官方 Authorization 契约获取、缓存和刷新 access_token，同时确保 AppSecret、access_token 与 refresh_token 不进入日志、RAW、前端、测试夹具或 Git。

本 PRP 已批准后续单独实现 Token Manager，但本次 docs-only approval gate 不写代码。实现仍需负责人另行下发后端工程师 Prompt；真实 Token 请求和领星业务 OpenAPI 调用不在本批准范围内。

## 2. Evidence

实现必须以 `docs/integrations/lingxing-auth-token-spec.md` 为证据基线。当前已确认：

- `POST /api/auth-server/oauth/access-token`，`multipart/form-data`，必填 `appId`、`appSecret`；
- `POST /api/auth-server/oauth/refresh`，`multipart/form-data`，必填 `appId`、`refreshToken`；
- 返回 `data.access_token`、`data.refresh_token`、`data.expires_in`；
- 每个 refresh_token 只能使用一次；
- 官方示例 `expires_in` 为 `7199`，但未明确承诺固定两小时；
- refresh_token 独立有效期、Token 持久化方式和提前刷新窗口均未由官方确认。

## 3. Approved implementation scope

负责人另行下发实现 Prompt 后，单独后端实现 PR 可以包含：

1. 后端内部 Token Manager，不暴露业务 API 或前端接口。
2. 获取 Token 与刷新 Token 的 endpoint-specific client contract。
3. access_token、refresh_token 与基于 `expires_in` 的过期状态管理。
4. refresh_token 单次使用保护：同一凭据范围内刷新必须串行，成功后原子替换两个 Token。
5. refresh_token 过期或无效时的受控重新获取流程。
6. 有上限的超时、重试与退避；认证错误不得无限重试。
7. 全链路 secret redaction 与安全错误映射。
8. synthetic/mock HTTP 测试；CI 不调用真实领星。
9. 必要的 Registry、后端模块清单和 API/运维文档同步。
10. 默认关闭的 `LINGXING_ENABLE_TOKEN_REQUESTS=false` 或等价安全开关。

## 4. Explicitly out of scope

- 本次 docs PR 中的任何后端或前端实现；
- 真实 access_token / refresh_token 获取；
- 领星业务 OpenAPI 调用；
- `raw_lingxing_api` 写入或任何 Token RAW 留痕；
- DIM、FACT、Core、read model、products 或 product_platform_listings 写入；
- full sync、定时任务、历史回补、Celery/Redis；
- Token 管理对外 API、管理页面或 Token 回显；
- 生产数据库连接、migration、ORM model 或新表；
- 新增依赖，除非后续 PRP 修订与负责人明确批准；
- 在仓库、日志、错误响应或文档保存真实凭据。
- Redis、共享缓存、加密共享存储或多实例 Token 协调。

## 5. Proposed internal contract

Token Manager 后续至少提供内部能力：

- `get_access_token()`：返回当前可用 access_token；调用方不得获得 refresh_token。
- `refresh_access_token()`：使用当前 refresh_token 完成一次串行刷新并原子替换状态。
- `invalidate()`：仅清除内存/获批存储中的失效状态，不调用业务 API。

返回给调用方的错误只能是稳定的内部错误类别和 request_id/trace_id，不得包含官方响应中的凭据、请求表单或 Token。

## 6. Security requirements

- AppID/AppSecret 必须通过后端环境 secret boundary 注入；配置文件只允许 placeholder 或 `secret_ref`。
- AppSecret、access_token 和 refresh_token 必须使用 `SecretStr` 或等价安全封装，禁止通过 `repr`、日志或异常暴露。
- access_token、refresh_token、AppSecret 不得进入日志、异常文本、metrics label、trace attribute、RAW、数据库审计 payload、测试 snapshot 或文档。
- access_token、refresh_token、AppSecret 不得进入 `raw_lingxing_api` 的 `response_json`、`request_body_json`、`extra_json` 或任何其他 RAW 字段。
- `.env.example` 只允许变量名和不可用 placeholder，不得包含示例凭据值。
- 前端不得接收、持有或刷新任何领星 Token。
- Token 请求不得复用通用业务 RAW writer。
- 官方错误 `2001001`、`2001002`、`2001005`、`2001008`、`2001009` 必须 fail closed；日志只记录脱敏错误类别。
- 必须防止并发重复使用同一个 refresh_token。
- 默认必须设置 `LINGXING_ENABLE_TOKEN_REQUESTS=false` 或等价安全开关；实现 PR 不得启用真实 Token 请求。
- 真实 Token 验证必须另开 controlled validation task，由负责人明确环境、操作人和安全边界。

## 7. Lifetime and refresh rules

- TTL 必须读取并校验响应 `expires_in`，不得硬编码固定两小时。
- 响应字段表与示例存在 string/number 差异，解析层必须接受官方已展示的两种表示并归一化为受限正整数。
- `expires_in` 的单位仍按官方文档未完全确认处理；单位解释和期限换算必须集中封装，便于后续取证后修正，不能散落在 client/cache 调用方。
- MVP 提前刷新窗口：正常情况下在剩余 10 分钟时刷新；若 Token 总有效期小于 10 分钟，则在剩余总有效期的 20% 时刷新。窗口基于集中封装后的期限值计算。
- refresh_token 只能使用一次；并发请求必须共享一个刷新结果或等待同一刷新动作。
- 刷新成功后必须原子替换内存中的 access_token 与 refresh_token，旧 refresh_token 不得再次使用。
- `2001003` 可触发 refresh/fallback 恢复；Token Manager 本身不负责重放业务请求。未来若单独批准业务请求重放，同一业务操作只能在初始请求后最多重试 2 次，非幂等请求仍需独立契约。
- `2001008` / `2001009` 允许回退到 GetToken；一次恢复链在初始 Token 请求后最多再请求 2 次，切换 endpoint 不得重置重试预算。
- Token endpoint 的其他可重试失败共用上述预算并使用短退避；不得无限循环或形成获取风暴。

## 8. Storage boundary

MVP 已批准使用单进程内存缓存，不持久化 Token，不创建 Token 表，不写 Redis，不写 `raw_lingxing_api`，不输出 Token 日志。

单进程内必须使用 lock/single-flight 防止并发刷新风暴，并保证 refresh_token 单次使用及 Token 对原子替换。多 worker/多实例共享、Redis 或加密共享存储后置为独立 PRP/任务，不得由本实现范围顺带加入。

## 9. Implementation files

具体文件 allowlist 必须由后续实现 Prompt 在当前仓库结构上确定。实现只允许 Token client、单进程内存缓存、刷新逻辑、secret redaction、安全设置占位和 mock 测试；不得借本 PRP 修改 Lingxing RAW Foundation、产品模块、前端或数据库层。

## 10. Test plan

后续实现必须只用 synthetic/mock HTTP，至少覆盖：

- 获取成功并解析 snake_case 返回字段；
- `expires_in` 为官方展示过的 string/number 两种类型；
- 刷新成功后同时替换 access_token 和 refresh_token；
- 多个并发调用只发生一次刷新；
- 旧 refresh_token 不被重复使用；
- `2001003`、`2001008`、`2001009` 和 `3001008` 的有界处理；
- AppSecret、Token 和表单值不出现在日志、错误、RAW 或 snapshot；
- 默认关闭真实 HTTP；
- `LINGXING_ENABLE_TOKEN_REQUESTS=false` 时 transport 调用次数为零；
- 不调用领星业务 endpoint；
- 不新增 Token 数据库表或 migration。

## 11. Validation gates

后续实现 PR 至少必须真实运行仓库已有的：

- Ruff format/lint；
- mypy；
- pytest；
- `git diff --check`；
- rule-pack check；
- targeted secret scan 与 scope scan。

未运行的检查必须写 `Not run` 与原因，禁止用 “should pass” 代替真实结果。

## 12. Owner approval record

| Item | Decision |
|---|---|
| Status | `Approved` |
| Approval date | `2026-09-11` |
| Approval type | Token Manager implementation gate |
| Main execution role | Backend Engineer |
| Storage | 单进程内存缓存；不落库、不写 Redis、不写 RAW、不记录 Token 日志 |
| Real requests | 实现 PR 只使用 MockTransport/synthetic response；真实 Token 验证另开 controlled validation task |
| Default gate | `LINGXING_ENABLE_TOKEN_REQUESTS=false` 或等价安全开关 |
| Lifetime | 以 `expires_in` 为准；不把 `7199` 写死为 SLA；单位仍未完全确认，解释与换算集中封装 |
| Early refresh | 剩余 10 分钟时刷新；总有效期小于 10 分钟时按剩余总有效期的 20% 提前刷新 |
| Refresh rotation | refresh_token 单次使用；刷新成功后原子替换内存中的两个 Token |
| Fallback | `2001008` / `2001009` 可回退 GetToken；一次恢复链在初始请求后最多再请求 2 次，切换 endpoint 不重置预算 |
| Rate limiting | 官方令牌桶容量 100，维度为 `appId + 接口 URL`；短退避、无无限循环 |
| Concurrency | 单进程 lock/single-flight；多实例共享后置独立任务 |
| Deferred | Redis/加密共享存储、多实例协调、真实 Token 请求、业务 API 调用、业务请求重放策略 |

批准只覆盖 Token Manager 后端实现。PRP Approved 不自动启动实现，仍需负责人下发独立后端实现 Prompt。

## 13. Stop conditions

出现以下任一情况必须停止并回报：

- 需要读取或输出真实 `.env`、AppSecret、Token、Cookie 或 Authorization；
- 需要调用领星业务 API；
- 需要写 RAW、数据库、migration、DIM/FACT/Core/read model；
- 需要让前端接收 Token；
- 需要新增依赖、修改 CI/部署或连接生产环境；
- 官方契约与取证文档不一致；
- 未收到负责人单独下发的后端实现 Prompt；
- 实际 worktree、分支或 allowlist 与批准 Prompt 不一致。

## 14. Rollback boundary

本 approval gate 可通过撤销 PRP 状态/Owner 决策和对应 Registry/Catalog 状态更新回滚。未来实现 PR 必须独立、可回滚，且不得影响已合并的 Lingxing RAW Foundation。

## 15. Acceptance checklist

- [ ] PRP 为 Approved，但实现必须等待负责人单独下发后端 Prompt。
- [ ] 官方事实与项目安全决策已分开记录。
- [ ] 没有把 `7199` 写成固定两小时 SLA。
- [ ] 没有真实 Token、AppSecret、访问凭据或业务数据。
- [ ] Token Manager 实现条目仅登记 `approved`；只有已合并的取证任务可登记 `implemented`。
- [ ] 没有修改 backend、frontend、old-system、依赖、脚本或 CI。
- [ ] 没有获取 Token 或调用业务 API。

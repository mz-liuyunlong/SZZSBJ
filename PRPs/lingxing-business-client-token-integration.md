# Lingxing Business Client Token Integration PRP

Status: `Approved`

Owner Approval Required: `Completed for Business Client Token Integration gate.`

Implementation Allowed: `Yes, but only after the owner issues a separate backend implementation prompt.`

Main Execution Role After Approval: `Backend Engineer`

## 1. Goal

将现有 `LingxingReadonlyClient` 的 Authorization 来源接入已实现的 `LingxingTokenManager`，由 client 在内部获取 access token 并构造认证 header。上层业务不得继续手动传入裸 Token 或完整 Authorization 值。

本 PRP 只批准下一轮独立后端任务的精确实现边界。本次 docs-only approval gate 不修改后端代码，不请求真实 Token，不调用真实 Lingxing 业务 API。

## 2. Evidence and current state

- Lingxing Token Manager Backend MVP 已在 PR #48 合并。
- GetToken / RefreshToken controlled validation 已在 PR #49 以脱敏事实记录；该验证不包含业务 API。
- Token 契约与安全证据见 `docs/integrations/lingxing-auth-token-spec.md`。
- 当前 `LingxingReadonlyClient` 已有 endpoint-specific contract、store allowlist、分页和真实调用总开关，但 Authorization 仍由构造参数直接注入。
- 当前 `LingxingTokenManager` 提供 `get_access_token()`、`refresh_access_token()` 和 `recover_from_access_error()`，Token 使用 `SecretStr` 封装并仅保存在单进程内存中。

上述事实不证明任何 Lingxing 业务 endpoint 已真实验证，也不授权 P0 endpoint sampling。

## 3. Approved implementation scope

负责人另行下发后端实现 Prompt 后，单独实现 PR 只允许：

1. 将现有 Lingxing readonly business client 的认证来源接入 `LingxingTokenManager`。
2. 通过构造函数依赖注入 Token Manager 或最小等价内部 provider；标准生产路径必须使用 `LingxingTokenManager`。
3. 在 client 内部、每次获批业务请求发送前获取 access token 并构造 Authorization header。
4. 移除上层业务手动传入裸 access token 或完整 Authorization 值的正常使用路径。
5. 对现有 approved readonly endpoint contracts 的 provider code `2001003` 实现一次有界恢复与重放。
6. 使用 fake Token Manager、`httpx.MockTransport` 和 synthetic values 增加或调整测试。
7. 如实现确有需要，最小调整 settings placeholder；不得加入真实凭据或默认开启真实请求。
8. 同一实现 PR 最小同步 Task Registry、Data Interface Registry 和 Backend Module Catalog。

## 4. Explicitly out of scope

- 新增 Lingxing 业务 endpoint；
- 扩大、放宽或绕过现有 endpoint contract；
- P0 endpoint sampling 或任何真实业务 API 调用；
- 真实 GetToken 或 RefreshToken 请求；
- RAW、数据库或 Redis 写入；
- DIM、FACT、Core、read model、products 或 `product_platform_listings` 写入；
- frontend、admin-frontend、FastAPI router 或业务读 API 接入；
- full sync、定时任务、历史回补或 Celery worker；
- 新表、migration、ORM model、索引或依赖；
- `.env` 读取、真实凭据示例、部署或生产配置修改。

## 5. Authentication integration contract

- 标准路径必须调用 `LingxingTokenManager.get_access_token()` 获取 `SecretStr` access token。
- Authorization header 只能在 `LingxingReadonlyClient` 内部构造并附加到出站请求；上层 capture/service/repository 不得接收、保存或拼接裸 Token。
- client 不得把 access token 转换为可被 `repr`、日志、异常、RAW envelope 或文档持久化的普通业务字段。
- 认证 header 必须保持现有 readonly client 行为：header 名为 `Authorization`，值来自 Token Manager 返回的 access token；本任务不得自行增加 `Bearer` 前缀、query token 或签名字段。若 provider contract 要求改变该格式，实施时必须停止并交由负责人确认。
- endpoint contract、store scope、page size、page count 和 URL 安全校验必须先于 Token 获取和 transport 调用。非法或 pending endpoint 必须在调用 Token Manager 前 fail closed。
- Token Manager 只提供认证材料，不得改变业务 endpoint、request body/query、store scope 或分页边界。

## 6. Configuration gates

- `LINGXING_ENABLE_REAL_CALLS=false` 继续作为 Lingxing business API transport 总开关；关闭时不得调用 Token Manager 或 HTTP transport。
- `LINGXING_ENABLE_TOKEN_REQUESTS=false` 继续作为真实 GetToken / RefreshToken 请求开关。
- 两个开关必须保持独立且默认关闭；启用其中一个不得隐式启用另一个。
- 本实现 PR 的测试全部使用 fake Token Manager、MockTransport 或 synthetic response，不得读取 `.env`。
- `.env.example` 如需变化，只能写变量名和安全默认值/placeholder，不得包含可复用凭据。

## 7. Provider code 2001003 recovery

仅当以下条件全部满足时，business client 才可执行恢复：

1. 请求已经通过现有 approved endpoint contract、store 和分页校验；
2. transport 返回可安全解析的 provider response；
3. provider code 明确为 `2001003`；
4. 当前业务请求尚未因 `2001003` 重放过。

恢复流程必须：

1. 调用 `LingxingTokenManager.recover_from_access_error(2001003)` 或等价已批准接口；
2. 使用恢复后 Token 在 client 内部重新构造 Authorization header；
3. 保持原 endpoint、method、query/body、store scope 和分页语义不变；
4. 对同一业务请求最多 replay 1 次，即初始业务请求之后最多再发送一次；
5. 第二次仍返回 `2001003` 时立即 fail closed，不得再次 refresh 或 replay；
6. 不对其他 provider code、未批准 endpoint 或 contract 校验失败执行该重放分支；
7. 不在重试、异常或测试失败信息中暴露 Token、header 或 provider 原始 payload。

Token Manager 自身的有界 Token 请求预算继续由 `PRPs/lingxing-token-manager.md` 管理；本 PRP 不放宽其最大尝试次数。

## 8. Security requirements

- access token、refresh token 和 AppSecret 必须继续使用 `SecretStr` 或等价安全封装。
- Token、Authorization 和凭据不得进入 `repr`、日志、异常、metrics label、trace attribute、测试 snapshot 或文档。
- Token、Authorization 和凭据不得进入 `response_json`、`request_body_json`、`request_params_json`、`extra_json`、RAW、数据库或 Redis。
- 错误只允许暴露稳定的内部类别、provider code 和非敏感 request/trace 标识；不得附带原始认证 payload。
- 测试值必须是不可复用 synthetic value；断言失败输出不得回显完整认证值。
- 真实业务 API 验证必须另开 controlled validation task，并由负责人明确批准环境、endpoint、store scope 和操作边界。

## 9. Implementation file boundary

后续实现 Prompt 必须在当前仓库状态上给出精确 allowlist，原则上仅限：

- `backend/app/integrations/lingxing/client.py`
- 必要且最小的 `backend/app/integrations/lingxing/` 内部接口文件
- `backend/tests/integrations/lingxing/` 中的相关测试
- `backend/app/core/config.py` 与 `backend/.env.example`，仅在确需安全 placeholder 时
- 本 PRP 指定的 registry/catalog 状态同步文件

不得借机修改 RAW model/repository/service、产品模块、API router、migration、依赖、前端、旧系统、scripts 或 CI。

## 10. Test plan

后续实现至少覆盖：

- 默认 `LINGXING_ENABLE_REAL_CALLS=false` 时 Token Manager 和 transport 调用次数均为零；
- 标准路径从 fake Token Manager 获取 synthetic `SecretStr`，并由 client 内部生成认证 header；
- 上层调用方不再传入裸 Token 或完整 Authorization 值；
- 现有三个 outbound-enabled endpoint contract 仍保持字段、store 和分页限制；
- 两个 pending endpoint 与所有非法 path 在 Token 获取和 transport 前拒绝；
- 任意新增字段、query/body 混用、absolute URL、`//host` 和 `..` 仍 fail closed；
- 首次 provider code `2001003` 触发一次 refresh/replay；
- replay 使用恢复后认证材料且业务 request contract 不变；
- replay 再次返回 `2001003` 时停止，业务 transport 总 replay 次数不超过 1；
- 其他 provider code 不触发该恢复分支；
- Token Manager 恢复失败时不发送第二次业务请求；
- Token、Authorization、AppSecret 不进入错误、日志、RAW envelope 或 snapshot；
- 测试全部使用 MockTransport/fake provider，不发生真实网络请求；
- 现有 RAW writer 行为、endpoint allowlist 和默认安全开关无回归。

## 11. Validation gates

后续实现 PR 必须真实运行仓库已有的：

- `uv sync --frozen`；
- Ruff format/lint；
- mypy；
- 定向与完整 pytest；
- `git diff --check`；
- rule-pack check；
- targeted secret scan；
- scope scan。

未运行项必须写 `Not run` 和原因，禁止以 “should pass” 代替实际结果。测试不得请求真实 Token 或业务 API。

## 12. Registry and catalog state

- Task ID：`lingxing-business-client-token-integration`。
- 任务状态：`approved`，不得在 implementation PR 合并前标记 `implemented`。
- 实现分支：`feat/lingxing-client-token-integration`。
- Implementation PR：`TBD`。
- Merge commit：`TBD`。
- Data Interface Registry 只能记录认证来源集成已获批、实现待合并；不得声称业务 API 或 P0 sampling 已验证。
- Backend Module Catalog 只能记录 integration gate 已获批；不得改变已实现 Token Manager 的事实状态，也不得预先声称 client integration 已实现。

## 13. Owner approval record

| Item | Decision |
|---|---|
| Status | `Approved` |
| Approval date | `2026-09-11` |
| Approval type | Business Client Token Integration implementation gate |
| Owner approval | Completed |
| Main execution role | Backend Engineer |
| Implementation start | 仅在负责人另行下发后端 implementation Prompt 后 |
| Token source | 标准路径使用 `LingxingTokenManager`；client 内部构造 Authorization header |
| Business endpoint scope | 仅现有 approved readonly endpoint contracts；不新增或放宽 endpoint |
| Real requests | 实现与测试均禁止真实 Token 请求和真实业务 API 调用 |
| Recovery | provider code `2001003` 可触发 Token Manager 恢复；同一业务请求最多 replay 1 次 |
| Storage | 不写 RAW、数据库或 Redis |
| Validation | fake Token Manager、MockTransport 和 synthetic values |
| Deferred | 真实 business API controlled validation、P0 endpoint sampling、任何同步或结构化写入 |

## 14. Stop conditions

出现以下任一情况必须停止并回报：

- 未收到负责人单独下发的后端实现 Prompt；
- 需要新增或放宽 endpoint contract；
- 需要调用真实 Token 或 Lingxing business API；
- 需要读取 `.env`、输出凭据或猜测 Authorization 格式；
- 需要写 RAW、数据库、Redis、DIM/FACT/Core/read model；
- 需要修改 frontend、API router、migration、依赖、scripts、CI 或生产配置；
- 需要对同一业务请求 replay 超过 1 次；
- 实际 worktree、分支、文件 allowlist 或验证环境与 Prompt 不一致；
- 发现 Token 或 Authorization 可能进入日志、异常、RAW 或 Git diff。

## 15. Rollback boundary

本 docs-only gate 可通过撤销本 PRP 与对应 registry/catalog 的 `approved` 记录回滚。未来实现必须是独立后端 PR，可通过撤销 client 的 Token Manager 注入与 `2001003` 恢复路径回滚，不得影响已合并的 Token Manager 本体。

## 16. Acceptance checklist

- [ ] PRP 状态为 `Approved`，但实现等待负责人单独下发后端 Prompt。
- [ ] 只批准现有 readonly client 的 Token Manager 认证来源集成。
- [ ] 没有新增或放宽 endpoint contract。
- [ ] `2001003` 最多触发一次业务请求 replay。
- [ ] 两个真实调用开关保持独立且默认关闭。
- [ ] 所有实现测试只使用 fake/MockTransport/synthetic values。
- [ ] 没有真实 Token、Authorization、AppSecret 或可复用凭据。
- [ ] 没有修改 backend、frontend、old-system、依赖、scripts 或 CI。
- [ ] Task/Registry/Catalog 保持 `approved`、PR/merge `TBD`，没有虚报 `implemented`。

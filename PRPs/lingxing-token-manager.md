# Lingxing Token Manager PRP

Status: `Draft — Pending Owner Review`

Owner Approval Required: `Yes`

Implementation Allowed: `No until owner changes Status to Approved and issues a separate implementation prompt`

## 1. Goal

为后端规划最小 Lingxing Token Manager：按官方 Authorization 契约获取、缓存和刷新 access_token，同时确保 AppSecret、access_token 与 refresh_token 不进入日志、RAW、前端、测试夹具或 Git。

本 PRP 当前只定义后续实现边界，不授权写代码、获取真实 Token 或调用领星业务 OpenAPI。

## 2. Evidence

实现必须以 `docs/integrations/lingxing-auth-token-spec.md` 为证据基线。当前已确认：

- `POST /api/auth-server/oauth/access-token`，`multipart/form-data`，必填 `appId`、`appSecret`；
- `POST /api/auth-server/oauth/refresh`，`multipart/form-data`，必填 `appId`、`refreshToken`；
- 返回 `data.access_token`、`data.refresh_token`、`data.expires_in`；
- 每个 refresh_token 只能使用一次；
- 官方示例 `expires_in` 为 `7199`，但未明确承诺固定两小时；
- refresh_token 独立有效期、Token 持久化方式和提前刷新窗口均未由官方确认。

## 3. Future implementation scope

负责人批准后，单独实现 PR 可以包含：

1. 后端内部 Token Manager，不暴露业务 API 或前端接口。
2. 获取 Token 与刷新 Token 的 endpoint-specific client contract。
3. access_token、refresh_token 与基于 `expires_in` 的过期状态管理。
4. refresh_token 单次使用保护：同一凭据范围内刷新必须串行，成功后原子替换两个 Token。
5. refresh_token 过期或无效时的受控重新获取流程。
6. 有上限的超时、重试与退避；认证错误不得无限重试。
7. 全链路 secret redaction 与安全错误映射。
8. synthetic/mock HTTP 测试；CI 不调用真实领星。
9. 必要的 Registry、后端模块清单和 API/运维文档同步。

## 4. Explicitly out of scope

- 当前 docs PR 中的任何后端或前端实现；
- 真实 access_token / refresh_token 获取；
- 领星业务 OpenAPI 调用；
- `raw_lingxing_api` 写入或任何 Token RAW 留痕；
- DIM、FACT、Core、read model、products 或 product_platform_listings 写入；
- full sync、定时任务、历史回补、Celery/Redis；
- Token 管理对外 API、管理页面或 Token 回显；
- 生产数据库连接、migration、ORM model 或新表；
- 新增依赖，除非后续 PRP 修订与负责人明确批准；
- 在仓库、日志、错误响应或文档保存真实凭据。

## 5. Proposed internal contract

Token Manager 后续至少提供内部能力：

- `get_access_token()`：返回当前可用 access_token；调用方不得获得 refresh_token。
- `refresh_access_token()`：使用当前 refresh_token 完成一次串行刷新并原子替换状态。
- `invalidate()`：仅清除内存/获批存储中的失效状态，不调用业务 API。

返回给调用方的错误只能是稳定的内部错误类别和 request_id/trace_id，不得包含官方响应中的凭据、请求表单或 Token。

## 6. Security requirements

- AppID/AppSecret 必须通过后端环境 secret boundary 注入；配置文件只允许 placeholder 或 `secret_ref`。
- access_token、refresh_token、AppSecret 不得进入日志、异常文本、metrics label、trace attribute、RAW、数据库审计 payload、测试 snapshot 或文档。
- 前端不得接收、持有或刷新任何领星 Token。
- Token 请求不得复用通用业务 RAW writer。
- 官方错误 `2001001`、`2001002`、`2001005`、`2001008`、`2001009` 必须 fail closed；日志只记录脱敏错误类别。
- 必须防止并发重复使用同一个 refresh_token。
- 默认必须关闭真实调用；启用真实 Token 请求需要单独负责人授权和明确环境。

## 7. Lifetime and refresh rules

- TTL 必须读取并校验响应 `expires_in`，不得硬编码固定两小时。
- 响应字段表与示例存在 string/number 差异，解析层必须接受官方已展示的两种表示并归一化为受限正整数。
- 提前刷新必须使用负责人批准的安全窗口，不能从官方示例自行推导。
- refresh_token 只能使用一次；并发请求必须共享一个刷新结果或等待同一刷新动作。
- `2001003` 可触发一次受控刷新与业务请求重试；具体业务请求集成另行批准。
- `2001008` / `2001009` 是否自动回退到 AppID/AppSecret 重新获取，须由负责人决定。
- `3001008` 采用有上限退避；不得无限重试或形成获取风暴。

## 8. Storage boundary

当前不批准 Token 持久化，也不创建 Token 表。负责人必须在实现前选择：

- 单进程、内存缓存的最小 MVP；或
- 经单独安全设计批准的加密共享存储。

如果部署形态为多 worker 或多实例，内存缓存不能自动视为安全的共享方案；应先解决 single-flight、刷新令牌单次使用和跨实例原子替换问题。

## 9. Implementation files

具体 allowlist 必须由后续实现 Prompt 在当前仓库结构上确定。不得借本 PRP 修改 Lingxing RAW Foundation、产品模块、前端或数据库层。

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

## 12. Owner decisions required

在本 PRP 可改为 Approved 前，负责人必须明确：

1. 首版使用单进程内存缓存，还是设计加密共享存储；
2. 允许真实 Token 请求的环境、操作人和启用开关；
3. 提前刷新安全窗口；
4. `2001008` / `2001009` 后是否允许自动重新获取及最大次数；
5. `3001008` 的退避和重试上限；
6. 多 worker/多实例下的 single-flight 与原子替换方案；
7. Token 读取权限、审计事件和告警接收方；
8. 官方文档未确认项是否需在受控环境做单独验证任务。

## 13. Stop conditions

出现以下任一情况必须停止并回报：

- 需要读取或输出真实 `.env`、AppSecret、Token、Cookie 或 Authorization；
- 需要调用领星业务 API；
- 需要写 RAW、数据库、migration、DIM/FACT/Core/read model；
- 需要让前端接收 Token；
- 需要新增依赖、修改 CI/部署或连接生产环境；
- 官方契约与取证文档不一致；
- 负责人决策尚未完成；
- 实际 worktree、分支或 allowlist 与批准 Prompt 不一致。

## 14. Rollback boundary

本 docs PR 可通过撤销两份新增文档和三处 candidate/planned 登记回滚。未来实现 PR 必须独立、可回滚，且不得影响已合并的 Lingxing RAW Foundation。

## 15. Acceptance checklist

- [ ] PRP 仍为 Draft，尚未授权实现。
- [ ] 官方事实与项目安全决策已分开记录。
- [ ] 没有把 `7199` 写成固定两小时 SLA。
- [ ] 没有真实 Token、AppSecret、访问凭据或业务数据。
- [ ] Registry/Catalog 仅登记 `candidate` / `planned`。
- [ ] 没有修改 backend、frontend、old-system、依赖、脚本或 CI。
- [ ] 没有获取 Token 或调用业务 API。


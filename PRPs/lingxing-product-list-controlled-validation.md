# PRP: Lingxing ProductLists Python Mock-Only Implementation Gate

Status: `Approved for Python Mock-Only Implementation`

Owner Approval Required: `Completed for Python mock-only implementation gate`

Implementation Allowed: `Yes, but only for Python backend mock-only implementation and only after the Owner issues a separate backend implementation prompt in an independent backend worktree`

Real Business API Validation Allowed: `No`

ProductLists Real Call Allowed: `No`

P0 Sampling Allowed: `No`

Dependency Approval: `Approved to add cryptography in the later backend implementation PR only if current Python dependencies do not already provide AES support`

Main Execution Role After Approval: `Backend Engineer`

Owner approval date: `2026-09-12`

## 1. 目标

批准后续独立 backend 任务，以 Python 在现有 Lingxing integration boundary 内实现以下 mock-only 能力：

1. `/erp/sc/routing/data/local_inventory/productList` 的精确 endpoint contract。
2. ProductLists 专用 Query Params auth/sign adapter。
3. 复用现有 `LingxingTokenManager` 获取 access token。
4. `MockTransport`、synthetic credential 与确定性签名测试。

本 PRP 不批准真实 ProductLists 调用、真实 Token 请求、P0 sampling、RAW/DB/Redis 写入或任何业务数据落地。

## 2. 证据定位与 Owner 判断

- 官方 ProductLists endpoint evidence：`docs/integrations/lingxing-product-list-endpoint-evidence.md`。
- 官方 query-sign evidence：`docs/integrations/lingxing-query-sign-auth-evidence.md`。
- 官方页面已确认 endpoint、业务字段、公共 Query Params 与高层签名步骤，但部分逐字节实现细节仍未完整说明。
- Owner 提供的已跑通参考项目补充确认了 ProductLists 调用与签名协议。本证据只用于批准 Python mock-only 实现，不改写为“官方文档已完整确认”，也不构成真实 API validation。
- 参考项目不是本项目的运行依赖。后续不得引入 Node、npm、`.mjs`、`.js` runtime，不得复制参考项目结构或重新实现 Token 获取链路。

## 3. Owner 批准的 ProductLists contract

| 项目 | 批准内容 |
|---|---|
| Method | `POST` |
| Path | `/erp/sc/routing/data/local_inventory/productList` |
| Content-Type | `application/json` |
| Accept | `application/json` |
| Auth query | `access_token`、`app_key`、`timestamp`、`sign` |
| App key | `app_key = appId` |
| Timestamp | 当前 Unix 秒级时间戳字符串，每次请求重新生成 |
| Body | JSON；空对象 `{}` 是已跑通参考协议；`offset`、`length` 如使用，必须位于 JSON body 而非 query |
| Success | ProductLists provider `code = 0`；列表位于顶层 `data`，总数位于顶层 `total` |

实现必须以独立 endpoint-specific contract 接入，不得放宽已有 approved readonly endpoint contracts，不得允许任意 path、absolute URL 或额外认证策略绕过。

## 4. Owner 批准的 query-sign contract

签名输入必须由业务 JSON body 参数与以下三项组成：

- `access_token`
- `app_key`
- `timestamp`

`sign` 是输出，不得参与自身签名。签名流程：

1. key 按默认字符串顺序排序。
2. 仅排除严格等于空字符串 `""` 的字段；`null`、`0`、`false` 保留。
3. array/object 使用 compact JSON serialization。
4. 按 `key=value&key=value` 拼接。
5. 计算 MD5 hex 并转大写。
6. 使用 appId 作为 AES key，执行 AES ECB 与 PKCS5/PKCS7 padding。
7. AES 输出使用 Base64。
8. 最终 `sign` 由 query params encoder 执行 URL encoding。

Python 实现必须集中封装排序、序列化、字节编码、摘要、padding、AES 与输出编码，并使用 synthetic inputs 固定测试行为。官方证据仍未覆盖的互操作细节继续作为真实 controlled validation 前的风险，不得借本批准宣称已由官方完整验证。

## 5. Token 与请求边界

- access token 必须来自现有 `LingxingTokenManager`，不得另写 Token 获取或刷新实现。
- `app_key`、`timestamp`、`sign` 和 access token 只允许在单次出站请求边界内构造和使用。
- 上层业务不得传入裸 Token、手工拼装认证 query 或读取 secret。
- `LINGXING_ENABLE_REAL_CALLS=false` 必须继续在 transport 前阻止真实业务请求。
- `LINGXING_ENABLE_TOKEN_REQUESTS=false` 必须继续阻止真实 Token 请求。
- 本 implementation PR 的全部 HTTP 测试必须使用 `MockTransport` 和 synthetic values。

## 6. 安全边界

以下认证材料不得进入日志、异常、RAW、DB、Redis、request envelope、response envelope、测试输出或文档：

- `access_token`
- `app_key`
- `timestamp`
- `sign`
- `appSecret`
- `Authorization`

安全业务参数与认证 query 必须分离。若现有 envelope 保存 request params，只能保存允许的业务 body 摘要，认证 query 必须在进入 envelope 前移除或脱敏。禁止记录完整请求 URL，因为 query 含认证材料。

## 7. 后续 backend implementation allowlist

负责人另行下发实现 Prompt 后，允许最小修改：

- 新增 `backend/app/integrations/lingxing/query_sign.py`。
- 最小修改 `backend/app/integrations/lingxing/client.py`。
- 最小补充 Lingxing integration settings 与 `backend/.env.example` placeholder/default（如确有需要）。
- 新增或修改 `backend/tests/integrations/lingxing/**` 的 mock-only tests。
- 若当前 Python 依赖没有 AES 支持，允许在同一 implementation PR 中增加 `cryptography`，并同步 `backend/pyproject.toml` 与 `backend/uv.lock`。
- 按项目规则最小更新 Task Registry、Data Interface Registry 与 Backend Module Catalog。

依赖批准不授权当前 docs PR 修改依赖，也不允许引入 Node/npm/JavaScript runtime。

## 8. 后续 backend implementation 明确非范围

- 真实 access token 或 refresh token 请求。
- 真实 ProductLists 或其他 Lingxing business API 调用。
- ProductLists controlled validation、P0 sampling、full sync 或历史回补。
- RAW、DB、Redis、DIM、FACT、Core、read model 或产品表写入。
- frontend、API router、service 业务接入或定时任务。
- 新增其他 endpoint 或放宽现有 endpoint contract。
- 读取 `.env`、业务 secret 文件或输出任何认证材料。
- 引入 Node、npm、`.mjs`、`.js` runtime 或参考项目结构。

## 9. Mock-only 测试要求

至少覆盖：

1. key 排序和 `key=value&key=value` 拼接。
2. 严格空字符串被排除，`null`、`0`、`false` 被保留。
3. array/object compact JSON serialization。
4. MD5 uppercase、AES ECB + PKCS5/PKCS7 padding、Base64 输出。
5. `sign` 不参与自身签名，`app_key = appId`，timestamp 为秒级字符串。
6. access token 和其他认证材料只在 HTTP query 中出现，不使用 Authorization header。
7. 空 JSON body 与含 `offset`/`length` 的 JSON body；分页字段不得进入 query。
8. ProductLists `code = 0` 成功与 provider error 安全失败。
9. endpoint contract 失败时不取 Token、不调用 transport。
10. 认证 query 不进入 envelope、日志、异常、RAW、DB 或 Redis。
11. 所有 HTTP 行为只使用 `MockTransport`，真实调用开关默认关闭。

## 10. Acceptance Criteria

- [x] Owner 已批准 Python backend mock-only implementation gate。
- [x] Owner 已批准在缺少现有 AES 支持时，由后续 backend PR 增加 `cryptography`。
- [x] Node/reference boundary 与 Python-only 实现要求明确。
- [x] Real Business API Validation、ProductLists Real Call 与 P0 Sampling 均保持 `No`。
- [x] 认证材料的非持久化、非日志和非 envelope 边界明确。
- [ ] Owner 另行下发 backend implementation Prompt。
- [ ] 后续 implementation PR 完成 Python 代码、mock-only tests 与 registry/catalog 更新。
- [ ] implementation PR 经 Review 并合并。
- [ ] 如需真实 ProductLists validation，另建 controlled validation gate 并由 Owner 明确批准。

## 11. 下一步

Owner 在独立 backend worktree 下发实现 Prompt，由 Backend Engineer 按本 PRP 用 Python 完成 mock-only ProductLists contract 与 query-sign adapter。真实业务 API 调用继续禁止，不能由本批准自动推进。

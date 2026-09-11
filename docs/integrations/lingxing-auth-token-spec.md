# 领星 Authorization Token 接口取证规格

Status: `Evidence Captured — Controlled Validation Completed`

Evidence date: `2026-09-10`

Controlled validation date: `2026-09-11`

## 1. 文档定位

本文记录 Lingxing Token Manager 所依据的官方接口事实、尚未确认项，以及负责人完成的脱敏受控验证结果。官方文档事实与受控运行观察必须区分；本文不授权业务 API 调用。

- 本次只读取领星官方 OpenAPI 文档，没有获取真实 Token，没有调用业务 OpenAPI。
- 本文不保存访问文档所需的凭据、企业 AppID/AppSecret、Token 或请求样例值。
- 官方页面没有说明的内容统一标记为“官方文档未确认”，不得据此编造实现契约。
- 官方文档可能变化；实现前应再次核对页面并记录复核日期。

## 2. 官方来源

| 主题 | 官方页面 | 本次用途 |
|---|---|---|
| 获取 Token | `https://apidoc.lingxing.com/#/docs/Authorization/GetToken` | 获取接口、请求字段、返回字段与成功/失败示例 |
| 刷新 Token | `https://apidoc.lingxing.com/#/docs/Authorization/RefreshToken` | 刷新接口、单次 refresh_token 语义与返回字段 |
| 全局错误码 | `https://apidoc.lingxing.com/#/docs/Guidance/ErrorCode` | Token 过期、refresh_token 失效与限流错误 |
| 接入指南 | `https://apidoc.lingxing.com/#/docs/Guidance/newInstructions` | 令牌桶算法和维度 |
| API 信息配置 | `https://apidoc.lingxing.com/#/docs/Guidance/AppID` | AppID/AppSecret 与 IP 白名单安全边界 |

## 3. 获取 access_token 和 refresh_token

| 项目 | 官方确认结果 |
|---|---|
| API Path | `/api/auth-server/oauth/access-token` |
| 协议 | HTTPS |
| HTTP Method | `POST` |
| Content-Type | `multipart/form-data` |
| 参数位置 | multipart form 字段；不是 JSON body。官方页面未列出 query 或认证 header 参数 |
| 必填字段 | `appId`、`appSecret`，均为 string |
| 签名 | 该 Authorization 页面未列出 `sign`；是否存在页面外要求，官方文档未确认 |
| timestamp | 该 Authorization 页面未列出；官方文档未确认 |
| nonce | 该 Authorization 页面未列出；官方文档未确认 |
| 令牌桶容量 | `100`；含义见第 7 节，不得解释为 100 次/分钟 |

返回对象字段：

| 字段 | 官方说明 | 取证注意事项 |
|---|---|---|
| `code` | 状态码 | 字段表标为 int，官方示例使用 string；实现需兼容并归一化 |
| `msg` | 消息提示 | 不得将可能含敏感上下文的原文无条件写入日志 |
| `data.access_token` | 请求令牌 | 敏感值，不得进入日志、RAW、文档或测试夹具 |
| `data.refresh_token` | 用于延续 access_token 有效期 | 敏感值；使用规则见第 4 节 |
| `data.expires_in` | access_token 过期时间 | 字段表标为 string，官方示例使用 number；单位未在字段说明中单独定义 |

官方成功示例中的 `data.expires_in` 为 `7199`。这与约两小时相符，但页面没有明确承诺“固定两小时”，也没有独立写明单位。因此当前结论是：

- 已确认：响应包含 `expires_in`，官方示例值为 `7199`。
- 未确认：固定有效期是否始终为两小时、单位是否由独立契约保证、服务端是否存在时钟或策略差异。

官方获取 Token 页面展示的失败示例为 `2001001`（AppID 不存在）。其他相关错误见第 6 节。

## 4. 刷新 access_token

| 项目 | 官方确认结果 |
|---|---|
| API Path | `/api/auth-server/oauth/refresh` |
| 协议 | HTTPS |
| HTTP Method | `POST` |
| Content-Type | `multipart/form-data` |
| 参数位置 | 根据 Content-Type 与请求参数表，按 multipart form 字段处理；官方页面未提供独立 query/JSON/header 契约 |
| 必填字段 | `appId`、`refreshToken`，均为 string |
| `refreshToken` 来源 | 获取 Token 接口返回的 `data.refresh_token` |
| 单次使用 | 官方明确每个 refresh_token 只能使用一次 |
| 签名 / timestamp / nonce | 该 Authorization 页面均未列出；官方文档未确认 |
| 令牌桶容量 | `100`；含义见第 7 节 |

刷新成功返回 `data.access_token`、`data.refresh_token`、`data.expires_in`。因为旧 refresh_token 只能使用一次，Token Manager 在刷新成功后必须原子替换 access_token 与 refresh_token，不能继续复用旧 refresh_token。

官方刷新页面成功示例中的 `data.expires_in` 同样为 `7199`；这仍只是示例证据，不是固定两小时的明确承诺。

refresh_token 的独立有效期、绝对过期时间字段和可提前刷新窗口：**官方文档未确认**。

## 5. 返回字段与未出现字段

| 关注项 | 结论 |
|---|---|
| access token 字段名 | `data.access_token` |
| refresh token 字段名 | `data.refresh_token` |
| access token 有效期字段 | `data.expires_in` |
| refresh token 有效期字段 | 官方文档未确认 |
| expiresAt / expireTime | 官方页面未列出 |
| token_type | 官方页面未列出 |
| scope | 官方页面未列出 |
| nonce | 官方页面未列出 |

## 6. 官方相关错误码

| 错误码 | 官方含义 | Token Manager 建议处理边界 |
|---|---|---|
| `2001001` | AppID 不存在 | fail closed；不得在错误或日志中回显 AppID/AppSecret |
| `2001002` | AppSecret 不正确 | fail closed；不得重试风暴；通知配置负责人 |
| `2001003` | access_token 缺失或过期 | 官方建议刷新 Token 后重试；业务请求重试次数需由后续 PRP 限定 |
| `2001004` | API 未授权 | 属于后续业务 API 授权问题；Token Manager 不得把它误判为 Token 过期 |
| `2001005` | access_token 不匹配 | fail closed；不得把 Token 写入诊断输出 |
| `2001006` | API 签名不正确 | 属于业务 API 签名检查；两个 Token 页面未列 `sign` 字段 |
| `2001007` | API 签名已过期 | 官方提示检查签名时间戳；两个 Token 页面未列 `timestamp` 字段 |
| `2001008` | refresh_token 过期 | 官方要求重新获取 access_token |
| `2001009` | refresh_token 无效 | 检查值或重新获取；不得重复并发使用同一 refresh_token |
| `3001001` | 缺少 access_token、sign、timestamp、app_key 查询参数 | 属于业务 API 请求契约，不能未经证据套用到 Token 接口 |
| `3001002` | 请求 IP 不在白名单 | 停止调用并由负责人检查受控环境的 IP 白名单 |
| `3001008` | 请求过于频繁 | 降低频率；退避和重试上限由后续 PRP 决定 |

全局错误码还列出业务 API 的签名和时间戳错误，但获取/刷新 Token 两个 Authorization 页面没有把 `sign`、`timestamp` 或 `app_key` 列为请求字段。不得把业务 API 鉴权参数未经证据直接加入 Token 接口。

refresh_token 失效后的官方恢复路径是重新获取 access_token。是否允许自动回退到 AppID/AppSecret 获取、允许次数和告警策略，必须由 Token Manager PRP 与负责人批准。

## 7. 重复获取与调用频率

- 两个 Token 页面均标注令牌桶容量为 `100`。
- 官方接入指南说明：每个请求消耗一个令牌，请求完成、异常或超时（2 分钟）时回收；令牌桶维度为 `appId + 接口 URL`。
- 因此不能把容量 `100` 解释为固定的“每秒/每分钟 100 次”。
- 触发限流时错误码为 `3001008`。
- 是否允许重复调用获取 Token 接口、旧 Token 是否立即失效、同一 AppID 可同时有效的 Token 数量：**官方文档未确认**。

Token Manager 必须避免并发刷新和重复获取风暴；具体锁、缓存和重试策略属于后续实现 PRP 决策，不由本文授权。

## 8. 安全边界

### 8.1 官方明确内容

- AppID/AppSecret 可访问企业全部数据，必须妥善保护，避免外泄。
- 重置 AppSecret 后，原 AppSecret 立即失效。
- IP 白名单要求公网 IP，不支持域名形式。

### 8.2 官方未确认内容

官方页面未确认以下实现策略：

- access_token / refresh_token 是否允许持久化以及允许的存储介质；
- 是否禁止日志输出 Token；
- 是否禁止将 Token 写入 RAW；
- 必须提前多少秒刷新；
- 多进程或多实例之间如何共享 Token；
- Token 加密、轮换和审计的具体实现。

### 8.3 本项目强制要求

无论官方是否说明，本项目必须遵守：

- AppSecret、access_token、refresh_token 只允许后端 secret boundary 使用，前端永远不得接收。
- 不得写入 Git、Markdown、PR、测试夹具、应用日志、错误响应或 `raw_lingxing_api`。
- 文档和 Registry 只能写 `secret_ref`，不能写真值。
- 真实凭据只能由获批环境注入；本地默认不得误连生产。
- 日志只允许记录脱敏后的事件、错误码、request_id/trace_id，不记录请求凭据或 Token。
- Token 是否持久化、保存位置、加密方式和读取权限必须经负责人单独批准。
- 提前刷新安全窗口必须由后续 PRP 明确，不能仅凭 `7199` 样例硬编码两小时。

## 9. 实现前未确认清单

| ID | 未确认项 | 阻塞影响 |
|---|---|---|
| U-1 | `expires_in` 的正式单位及是否固定约两小时 | 阻塞硬编码 TTL；实现必须以响应值为准 |
| U-2 | refresh_token 独立有效期 | 阻塞持久化与轮换时限设计 |
| U-3 | 重复获取 Token 对已有 Token 的影响 | 阻塞主动重新获取策略 |
| U-4 | access_token / refresh_token 官方允许的持久化方式 | 必须使用更严格的项目安全决策 |
| U-5 | 提前刷新窗口 | 需要负责人确定保守安全边际 |
| U-6 | 多 worker/多实例共享与单次 refresh 并发策略 | 阻塞生产部署形态选择 |
| U-7 | 限流后的退避、最大重试次数和告警 | 阻塞自动重试策略 |
| U-8 | Token 接口是否还有页面外的签名或 IP 环境前置条件 | 实现前需在受控环境复核；本任务不调用接口 |

## 10. Controlled validation 记录

负责人于 `2026-09-11` 在本机完成仅限 GetToken 与 RefreshToken 的 controlled validation。以下内容仅为脱敏事实，不包含凭据、完整请求体或完整响应体。

| 项目 | 脱敏观察 |
|---|---|
| 验证范围 | 仅 GetToken 与 RefreshToken；未调用任何 Lingxing 业务 API |
| GetToken | 成功；access token 与 refresh token 字段均存在；观察到的 `expires_in` 为 `7199` 和 `7092`；已计算 `refresh_after` |
| RefreshToken | 成功；新 access token 与新 refresh token 字段均存在；refresh token 与内存 snapshot 已轮换；旧 refresh token 未复用 |
| access token 字符串 | 立即刷新时未变化；实现不得以 access token 字符串是否变化作为刷新成功条件 |
| TTL 解释 | 观察值为 numeric TTL-like value，与当前按秒集中处理兼容；`7199` 不得视为固定两小时 SLA |
| 数据与存储边界 | 未写 RAW、数据库或 Redis；未读取 `.env` 文件；未输出任何 secret |
| 后续边界 | 真实业务 API 集成和 P0 endpoint 采样仍是独立未来任务 |

本次受控验证只确认已批准 Token Manager 对 GetToken/RefreshToken 的最小真实交互，不证明任何业务 API、RAW 写入、同步任务或 P0 endpoint 已验证。

## 11. 取证结论

官方文档取证已用于批准 `PRPs/lingxing-token-manager.md`，Lingxing Token Manager Backend MVP 已在 PR #48 合并。本次 controlled validation 补充了 GetToken/RefreshToken 的脱敏运行证据，但不扩大到业务 API、RAW、数据库、Redis、P0 endpoint 采样或同步能力。

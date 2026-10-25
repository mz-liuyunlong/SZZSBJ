# Walmart Monitor RAW Ingestion 数据源决策

- 调查日期：2026-10-22
- 调查人：Codex（只读仓库证据调查）
- 目标 method/path：`POST /api/integrations/walmart-monitor/raw-events`
- 业务用途：接收 Walmart 监控程序主动推送的完整统一 RAW 事件，保留可回放来源证据
- 接口总体状态：`READY_FOR_PRP`
- 是否包含 `NEED_OWNER_DECISION`：否
- 负责人批准状态：监控主动推送、单一 RAW、暂不写 Listing 的数据源方向已确认；具体 PRP 待确认
- 关联证据：监控项目 `lib/integrations/outbox.ts`、`lib/types.ts`、`lib/raw-monitor-data.ts`、`docs/server-result-sync.md`
- 决策文件路径：`docs/data-sources/decisions/walmart-monitor-raw-ingestion-decision.md`
- 后续接口 PRP：`PRPs/walmart-monitor-raw-ingestion.md`

## 1. 前置调查

| 前置调查项 | 证据位置与调查结论 |
|---|---|
| 旧页面 | 不适用。本接口是服务到服务的 RAW 接收入口，不新增页面。 |
| 旧 API | 不适用。新系统当前没有 Walmart 监控结果接收 API。 |
| 旧接口文件位置 | 不读取或修改 `old-system/**`。生产者契约来自独立监控项目的当前代码与 `docs/server-result-sync.md`。 |
| 读取表 | 接收端不读取业务表；仅按 `event_id` 查询本任务新增的 RAW 表完成幂等校验。 |
| 表写入方 | 新系统 Walmart Monitor ingestion service；每个逻辑检查只追加一个统一事件。 |
| cron / 脚本 / 外部 API | 生产者本地 outbox 主动 POST；接收 route 不调用 Walmart、Decodo、Lingxing 或其他外部 API，不触发 Celery。 |
| 人工写库入口 | 无。禁止手工修订 RAW payload。 |
| 外部平台重新获取可能性 | 不保证。生产者会重试投递，但原始页面/Decodo 响应可能无法再次取得，因此首份有效 RAW 必须完整留存。 |
| 少量配置数据可行性 | 仅需要部署环境中的 bearer `secret_ref`；真值不进入代码、文档、日志、响应或 RAW。 |
| 短期策略 | 接收 `walmart-monitor.raw.v1`，严格校验、幂等、append-only 保存至独立 L2 RAW 表；不解析进业务层。 |
| 长期策略 | 后续独立 PRP 建设 RAW → 标准化/ODS → 监控当前态/历史，再决定 Listing 展示字段。 |

## 2. 数据集分类

| 数据集或字段组 | 业务用途 | 当前权威来源 | 分类 | 短期策略 | 长期策略 | 退出条件或切换点 | 需负责人确认 |
|---|---|---|---|---|---|---|---|
| 监控投递事件及来源 payload | 保存采集证据 | Walmart Product Status 监控程序 | `REBUILD_SYNC` | 单一事件写独立 L2 RAW；不拆 Chrome/Decodo 表 | 版本化解析并发布标准化层 | 新 schema_version 需独立兼容评审 | 否 |
| 接收/幂等元数据 | 防重、审计、重放定位 | 新系统接收服务 | `NEW_SYSTEM_OWNED` | `event_id` 唯一；记录 hash、大小、捕获/接收时间和安全计数 | 接入统一治理/血缘时保留原 event identity | 后续治理迁移必须可核对 hash 和数量 | 否 |
| `final_observation` 解析快照 | 辅助诊断，不作为业务真相 | 监控程序解析结果 | `ARCHIVE_ONLY` | 原样保存在 RAW payload 内 | 后续 parser 只能从 RAW 派生并记录版本 | 标准化层上线且有独立 PRP | 否 |

## 3. 分层、粒度与权威边界

- L0：Walmart 页面、Decodo 响应和监控程序采集结果。
- L1：HTTP 投递 envelope（schema/event/producer/attempt/target 元数据）。
- L2：独立 `raw_walmart_monitor_events`，一行代表一个逻辑监控检查事件。
- 本任务不建设 L3+，不写 Listing、Product、GPT、归档、Daily Sales 或 Order Profit。
- RAW 是审计和回放证据，不是业务权威；前端和业务 API 禁止直接查询。
- 两种监控模式统一保存到 `attempts`，不得按 provider 拆两张 RAW 表。

## 4. 数据血缘

| 接口字段 | 源系统/字段 | 目标 | 转换 | 时间/币种 | 风险与门禁 |
|---|---|---|---|---|---|
| `schema_version` | producer payload | searchable envelope + payload | 仅接受 `walmart-monitor.raw.v1` | 不适用 | 未知版本拒绝 |
| `event_id` | producer stable event ID | unique idempotency key | trim 后原样；header 必须相同 | 不适用 | 同 ID 不同 hash 返回冲突 |
| `captured_at` | check capture time | UTC-aware timestamp + payload | 要求带 offset；按 instant 保存 | UTC | 不猜测时区 |
| `producer.*` | monitor instance/check/run | payload +安全 envelope 字段 | 原样；长度限制 | 不适用 | 不作为业务身份 |
| `targets[]` | source rows | payload only | 保留 `source_account_ref + store_id + item_id`；不推断 SKU/MSKU/ItemID | 不适用 | 至少一个 target；不写 Listing |
| `attempts[]` | Chrome/Decodo/fallback | payload only | 保留顺序、provider、outcome | 不适用 | attempt_no 必须唯一且递增可排序 |
| `source_payloads[]` | gzip source artifact | payload only | base64 解码、压缩大小、解压大小、SHA-256 全部校验 | 不适用 | 失败即整事件拒绝；限制压缩/解压大小 |
| `final_observation` | producer parsed snapshot | payload only | 不解析为业务列 | 来源时间随事件 | 不是业务权威 |
| `received_at` | receiver | searchable envelope | 服务端 UTC 生成 | UTC | 与 captured_at 分离 |

## 5. 安全、质量和保留

- 使用部署环境注入的 `WALMART_MONITOR_INGEST_TOKEN` `secret_ref`；至少 32 位 ASCII，默认未配置并 fail closed。
- 使用 constant-time compare；认证失败、校验错误和日志不得包含 token、完整 payload、URL 或商品明细。
- API 不提供 RAW 读取端点；仅返回接收 ID、event ID、duplicate 状态和 received time。
- 提议单事件最多 100 targets、20 attempts；每个压缩 artifact 最多 10 MiB、解压后最多 25 MiB。
- 每个 artifact 必须通过 base64、gzip、byte size、stored size 和 SHA-256 校验。
- V1 不自动删除、覆盖或归档；生产保留/清理必须另行批准。
- migration 只新增独立表，不修改现有线上业务表。

## 6. 最终建议

- 接口总体状态：`READY_FOR_PRP`
- 推荐短期策略：独立、append-only、无读取 API 的 L2 RAW 接收端。
- 推荐长期策略：以独立 PRP 建设 parser/ODS/current/history，再决定 Listing 字段。
- 旧库退出条件：不适用；运行时从不读取旧库。
- 迁移或同步边界：仅本地代码和 migration；不授权生产 migration、部署、回填或真实投递。
- 主要风险：大 payload、压缩炸弹、事件重放冲突、服务 token 泄漏；均在 PRP 中设硬门禁。
- 待负责人决定：无数据源阻塞；PRP 具体实现范围仍需负责人确认。

## 7. 负责人决定记录

- 已确认方向：监控端主动推送完整 RAW；新系统单独保存一个统一 RAW；暂不直接写 Listing；保留 `monitoring_eligible` 供后续资格规则。
- 本文件只允许进入 PRP；不代表生产数据库、部署、真实投递或后续解析已获授权。

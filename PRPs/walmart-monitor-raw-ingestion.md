# Walmart Monitor RAW Ingestion PRP

## 1. Approval

```text
PRP Status: Approved
Implementation Authorized: Yes — local branch implementation only
Source Decision Gate: READY_FOR_PRP
Main Role: Backend Engineer
Worktree: <project-root-name>-walmart-monitor-raw-ingestion-v2
Branch: codex/walmart-monitor-raw-ingestion-v2
Base: a35c690faa7475d38165f179d785b05ec7be1df6
Source Decision: docs/data-sources/decisions/walmart-monitor-raw-ingestion-decision.md
```

## 2. Goal

新增一个受保护的机器到机器接收接口，将 Walmart Product Status 监控程序发送的
`walmart-monitor.raw.v1` 统一事件完整、幂等、append-only 地保存在独立 L2 RAW 表中。
本任务只负责接收和保存，不解析进 Listing 或任何业务表。

## 3. Why

- 历史监控结果和未来监控结果需要进入新系统，且必须保留完整 RAW 才能重放和重新分析。
- Chrome Extension、Decodo API 和 fallback 是同一逻辑检查的不同 attempt，不能拆成两套 RAW。
- 直接写 Listing 会提前固化尚未确认的字段和规则，因此本期必须保持 RAW-first。

## 4. Scope

### In scope

- `POST /api/integrations/walmart-monitor/raw-events`。
- 专用 service bearer token、最小 permission principal 和 fail-closed 配置。
- `raw_walmart_monitor_events` 独立 L2 RAW 表、SQLAlchemy model、repository、service。
- `event_id` + canonical payload hash 幂等和并发冲突处理。
- gzip/base64、大小和 SHA-256 完整性校验。
- Alembic `0048`（以实现时唯一 head 为准）新增表 migration。
- synthetic/mock-only 单元/API/migration 测试、OpenAPI/API 文档、registry/catalog/handoff。

### Out of scope

- `GET /api/integrations/walmart-monitor/targets` 商品来源接口；必须另立任务/PR。
- 监控程序代码、SQLite、历史数据导入、类目补采或真实结果投递。
- RAW parser、ODS、current/history、Listing 字段或页面。
- GPT、归档、标签、生命周期、负责人、备注和 Listing identity。
- Celery、调度、通知、外部 API、对象存储、自动清理或生产迁移/部署。
- `old-system/**`、frontend、依赖和锁文件。

## 5. Backend module design

### API Route

- Prefix: `/api/integrations/walmart-monitor`
- Endpoint: `POST /raw-events`
- Route 只处理 request、`Idempotency-Key`、认证/权限依赖、schema 和统一 envelope。

### Pydantic Schema

- 只接受 `schema_version="walmart-monitor.raw.v1"`。
- `targets`：1..100；`attempts`：1..20。
- 外部 ID 全部按 string 保存，不把 SKU/MSKU/ItemID 互相推断。
- `captured_at` 必须是带 offset 的 datetime。
- `final_observation` 仅作为 RAW snapshot 保存，不进入业务字段。

### Service

- 生成稳定 canonical JSON bytes 和 SHA-256。
- 验证每个 artifact 的 base64/gzip/byte size/stored size/hash。
- 对同 event/hash 返回 duplicate；同 event/不同 hash 返回 409。
- 成功写入后 commit；任何异常由 request transaction rollback，不留半条事件。

### Repository

- 只访问 `raw_walmart_monitor_events`。
- 使用 PostgreSQL 原子 conflict handling 防止并发重复事件产生 500 或双写。
- Repository 不创建 engine，不直接 commit/rollback。

### Model / Migration

- 一行粒度：一个 producer logical check event。
- 安全 envelope 列：ID、event/schema、producer IDs、capture/receive time、provider/outcome、target/attempt count、hash、bytes。
- `payload_json` JSONB 保存完整请求，包括压缩后的 source payload。
- `event_id` 唯一；`captured_at` 与 `raw_hash` 普通索引；不外键关联现有业务表。
- migration 只新增表；downgrade 可删除新表，但生产执行仍需单独批准。

### Integration / Celery

- 不实现 outbound integration；不调用外部 API。
- 不新增 Celery task、beat schedule 或重处理 worker。

### 权限与操作日志

- 专用 principal：`walmart-monitor-service`。
- permissionKey：`integrations:walmart-monitor:write`。
- token：`WALMART_MONITOR_INGEST_TOKEN` 的部署环境 `secret_ref`，`SecretStr`，至少 32 位 ASCII。
- 仅精确 POST 路径可解析该 machine token；不加入 public allowlist，不授予其他路由。
- RAW 默认不可读；本任务不提供 read permission 或 payload API。
- event envelope 是接收审计；日志只允许 request_id、error_code 和安全计数。

### 测试方案

- schema/version/time/required fields。
- token 缺失、错误、非 ASCII、过短配置 fail closed；secret 不泄漏。
- header/body idempotency mismatch。
- 首次写入、相同重放、同 ID 不同内容冲突、并发 replay。
- gzip/base64/hash/size 校验、压缩炸弹上限。
- 完整 payload（含类目、两种 provider attempt）被原样保存。
- 表与现有业务表无 foreign key；不写 Listing/GPT/archive。
- migration upgrade/downgrade 用隔离 PostgreSQL；无授权 DB 时明确 skip。

## 6. Data contract

### Request

```text
method: POST
path: /api/integrations/walmart-monitor/raw-events
headers:
  Authorization: Bearer <secret_ref>
  Idempotency-Key: exactly equals event_id
content-type: application/json
```

顶层字段：

- `schema_version`
- `event_id`
- `captured_at`
- `requested_provider`
- `producer { instance_id, check_id, run_id? }`
- `targets[] { source_account_ref, store_id, item_id, ...source descriptors, monitoring_eligible }`
- `attempts[] { attempt_no, provider, outcome, source_payloads[] }`
- `final_observation`

每个 `source_payloads[]`：

- `kind`
- `content_type`
- `compression="gzip"`
- `sha256`
- `byte_size`
- `stored_byte_size`
- `data_base64`

### Response

统一 `{ success, data, error, meta, request_id }` envelope；`data` 只含：

- internal event UUID
- `event_id`
- `accepted`
- `duplicate`
- `received_at`

绝不返回 RAW、source identifiers、artifact、token 或解析商品内容。

### Error codes

- `UNAUTHORIZED`
- `FORBIDDEN`
- `VALIDATION_ERROR`
- `MONITOR_IDEMPOTENCY_KEY_INVALID`
- `MONITOR_EVENT_CONFLICT`
- `MONITOR_RAW_PAYLOAD_INVALID`
- `MONITOR_RAW_PAYLOAD_TOO_LARGE`

## 7. Limits and data quality

- compressed artifact ≤ 10 MiB；uncompressed artifact ≤ 25 MiB。
- artifact 声明大小必须等于实际 bytes。
- gzip 解压后 SHA-256 必须等于声明值。
- `event_id` 唯一，重复内容必须 hash 相同。
- target 稳定键要求非空 `source_account_ref + store_id + item_id`。
- attempt_no 不得重复；provider/outcome 保留 source enum 文本但有长度上限。
- 任何校验失败拒绝整个 event，不做部分保存。

## 8. Database layers and lineage

- Written layer: L2 RAW；envelope 同时承担 L1/L12 接收证据。
- Authoritative source: monitor producer for the emitted event；RAW 不是 Listing 业务权威。
- Writer: Walmart Monitor ingestion service。
- Reader: 本 PR 无 reader；未来 parser 需独立 PRP。
- Freshness: producer outbox 主动推送并重试；API 不承诺业务实时性。
- Retention: V1 no auto-delete；未来 archive/delete 单独审批。
- Rollback: 停止配置 token 即 fail closed；代码回滚移除 router/auth seam；表保留待审计，生产 drop 需单独授权。

## 9. Documentation and registry

- Markdown API doc required。
- OpenAPI metadata required。
- 更新 `docs/api/README.md`、`docs/BACKEND_MODULE_CATALOG.md`。
- 更新 Task Registry 和 Data Interface Registry。
- 无页面，因此 SOP/PageShell/Playwright 不适用。

## 10. Validation gates

执行前先读取项目 `pyproject.toml`、CI 和现有脚本，只运行真实存在的命令：

```text
targeted pytest
full backend pytest
ruff format --check
ruff check
compile/import check
offline Alembic heads/check
isolated PostgreSQL migration test when TEST_DATABASE_URL is explicitly available
git diff --check
rule-pack and exact scope/secret/RAW-artifact checks
```

## 11. Allowlist

实现批准后仅允许修改：

- `backend/app/modules/walmart_monitor/**`
- `backend/app/core/auth.py`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/alembic/env.py`
- `backend/alembic/versions/20261022_0048_walmart_monitor_raw_events.py`
- `backend/.env.example`
- `backend/tests/modules/test_walmart_monitor_integration.py`
- `backend/tests/core/test_backend_api_foundation.py`（仅 machine auth 回归，如必要）
- `backend/tests/db/test_alembic_scaffold.py`
- `docs/api/walmart-monitor-integration.md`
- `docs/api/README.md`
- `docs/BACKEND_MODULE_CATALOG.md`
- `docs/data-sources/decisions/walmart-monitor-raw-ingestion-decision.md`
- `PRPs/walmart-monitor-raw-ingestion.md`
- `docs/data-registry/DATA_INTERFACE_REGISTRY.md`
- `docs/tasks/TASK_REGISTRY.md`
- `CODEX_HANDOFF.md`

## 12. Forbidden actions

- 不修改 `main`/`dev` 或 `old-system/**`。
- 不连接生产数据库，不执行生产 migration，不部署或重启服务。
- 不调用 Walmart/Decodo/Lingxing，不运行监控或同步。
- 不修改 Listing、GPT、归档、产品、财务和现有 RAW 表。
- 不输出真实账号、ItemID、SKU/MSKU、URL、payload、token 或密钥。
- 不新增依赖、对象存储、Celery、frontend 或第二套同步框架。

## 13. Acceptance checklist

- [x] Project Owner 明确批准本 PRP 进入实现。
- [x] Endpoint、schema、response_model、统一 envelope 和 OpenAPI 完成。
- [x] machine token + permission fail closed，secret 不泄漏。
- [x] RAW table 与业务表完全隔离。
- [x] 完整性、大小、幂等和并发门禁通过。
- [x] 相同事件安全重放，不同内容冲突拒绝。
- [x] 不提供 RAW read API，不写任何现有业务表。
- [x] migration、测试、API doc、catalog/registry/handoff 完成。
- [x] 所有本地验证如实记录；生产操作均未执行。

## 14. Owner approval block

```text
Decision: approved
Approved scope: Sections 2–13 of this PRP
Approved limits: Local implementation and synthetic validation only
Approved by: Project Owner (conversation approval)
Approved date: 2026-10-22
Notes: PRP approval authorizes local implementation only, not production migration/deployment/delivery.
```

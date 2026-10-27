# PRP: WFS 费用异常自动检测 V1

- Status: Approved for implementation；implementation ready for PR review, not merged
- Main execution role: Backend Engineer（含现有前端页面最小集成）
- Source Decision: `docs/data-sources/decisions/wfs-fee-anomaly-auto-detection-decision.md`
- Branch: `feat/wfs-fee-anomaly-auto-detection`
- Production execution authorized: No

## Goal

在现有 Warehouse WFS、Product Management、Integration Sync、案件审批和 Celery 架构上形成可在隔离环境运行的完整链路：结算采集 → RAW/ODS → 订单费率 → 标准费率与销量 → 异常金额 → dry-run/幂等案件候选 → 现有页面 → 默认关闭的每日调度。

## Required implementation

1. 统一订单级 WFS 算法：T-2/60 天、完整分页、订单次数众数、并列按最近日期再金额确定；分别输出 `sample_units`, `fee_orders`, `mode_count`。
2. 为 `/basicOpen/multiplatform/profit/report/order` 增加专用 client/handler，使用现有 Token Manager、endpoint contract、Integration Sync run/work item/RAW blob/request ref。
3. 最小扩展 `fact_walmart_wfs_fee_actual`，保存订单号、销量、签名金额、结算日和 RAW request ref；幂等来源行更新且保留 RAW 历史。
4. 新增新系统累计销量读取器，严格使用 account/store/MSKU 和已确认 listing identity，返回覆盖状态和数据截止日。
5. 复用 Product Management 动态计算，分别计算旧口径估算、逐单理论超额、全样本净差额，并输出完整质量状态。
6. 复用 `ops_wfs_fee_anomaly_cases`，仅满足全部门槛时插入 `future_lingxing_profit_order/pending_confirm`；数据库冲突即跳过，禁止覆盖人工字段。
7. 多店铺批处理、单店隔离、锁/幂等、受控重试和 Integration Sync 状态；`WFS_AUTO_DETECT_ENABLED=false` 与 `WFS_AUTO_CASE_CREATE_ENABLED=false` 独立门禁。
8. 扩展现有 WFS API 和页面，列表只展示核心指标，详情展示证据、来源、金额构成、时效与质量问题；保留原人工流程。

## API contract

- 保持现有 `/api/warehouse/wfs-fee-alerts` 与 `/api/warehouse/wfs-fee-cases` 兼容。
- 新增 dry-run preview 与 run status 时必须使用统一 envelope、response model、permissionKey/data scope 和安全错误码。
- 未授权正式执行、部分采集、身份冲突、缺少标准费或销量覆盖必须 fail closed。

## Security and permissions

- 外部请求仅通过现有 Lingxing client；认证 query/header 不进入 RAW、DB、envelope、日志或异常。
- `view`、`dry-run`、正式执行/案件写入分别使用既有 WFS 权限体系；前端隐藏不替代后端校验。
- 不打印 RAW payload、商品敏感字段、Token、Secret 或 Authorization。

## Migration plan

- 只新增 additive migration，基于当前单一 head。
- 不修改历史 migration；upgrade/downgrade 对新增列和约束可逆。
- 生产 migration 不在本任务执行。

## Test plan

- 算法：多行/多件/跨月/退款/重复/众数与并列/货币/日期/缺失身份。
- 采集：MockTransport、完整分页、总数变化、失败/重试/上限、RAW 回指、幂等和店铺隔离。
- 销量与定价：默认/有效/覆盖规则、冲突、缺失、日期口径和三类金额。
- 案件：dry-run 零写入、首次/重复/并发、人工/跟进/归档/追回保护、事务失败。
- 调度：两个开关、重复调度、锁、单店失败、重试、状态。
- 前端：列表/详情/证据/陈旧/权限/旧案件兼容。
- 执行 Ruff、mypy、pytest、Alembic heads、frontend lint/typecheck/Vitest/build 和 rule pack。

## Acceptance

- 代码层链路全部接线且隔离测试通过；没有把 mock/计划写成生产已验证。
- 已知商品数值仅用于脱敏夹具回归，不作为业务常量。
- 自动检测与自动建案默认关闭；生产迁移、采集、案件写入、Beat 启用和部署仍需单独 Owner 授权。

## Owner-review hardening record

- 正式时效以 `detection_executed_at.date()` 与最新结算日计算；历史窗口结束日不能冒充检测日。Backtest 必须显式标记，且禁止写案件或检测证据。
- 每个账号/店铺/窗口由 `gov_wfs_settlement_collections` 独立证明完整性。只有分页总数稳定、全部行已分类、无无效/重复/缺失身份/未知店铺且事实数一致的 `verified` collection 才能检测。
- 销量存在不等于生命周期完整。只有 Listing 生命周期起点与连续成功的 `saleStatPageList` 同步窗口共同覆盖所需日期，才标记 `complete`；否则为 `partial`、`missing` 或 `unknown` 并阻断自动立案。
- `storeId` 是请求范围内的稳定店铺身份；`storeName` 仅作描述。`CS*` 是可计数的业务排除项，不等同于异常行。
- 仓库证据尚不能证明 profit-order 每个物流费行都属于 WFS，因此 `WFS_SETTLEMENT_SCOPE_VERIFIED=false` 默认保持 fail closed。只有后续受控合同证据与 Owner 授权才能开启。
- 标准费除来源必须已确认外，`historical_applicability` 还必须为 `historical_confirmed`；`current_only` 仅保留理论估算并进入 `REVIEW_REQUIRED`，不得自动建案。
- 多店采集中任一店铺失败都会令本次 run 为 `failed`；返回可以说明部分店铺完成，但不得把不完整 run 持久化为成功。
- 案件主体仍为 insert-only；每次新的 verified collection 可追加独立检测证据，历史人工字段、跟进、审批、归档、索赔和追回状态不被自动覆盖。
- 0061 在隔离 PostgreSQL 16 上完成带历史合成事实/人工案件的 0060→0061、案件并发/回滚测试、0061→0060→0061。生产索引重建仍存在锁风险，需单独低峰变更计划和生产授权。

## Performance record

- 标准费用批量读取：100 个身份固定 3 次 `execute` + 2 次 `scalars`；销量与覆盖证明固定 3 次查询；结算事实每批为 1 次 Listing 身份查询 + 1 次批量 upsert。
- 合成纯计算基线（本机、非生产）：1 店/100 SKU 为 collection `1.88 ms`、detection `15.61 ms`、峰值 `0.31 MiB`；9 店/1,000 SKU 为 `18.56 ms`、`164.09 ms`、`2.90 MiB`；20 店/10,000 SKU 为 `241.77 ms`、`1804.87 ms`、`28.98 MiB`。
- 上述是合成 parser/detection 资源基线，不是数据库或真实 provider SLA；生产容量仍需受控观测。

## Final independent acceptance record（2026-10-27）

- GitHub PR HEAD: `6695114a8594ad585e0556e6491a3b0f7e1f430e`；PR #257 为 Open、非 Draft、mergeable，该远端 HEAD 的 13 个 GitHub checks 全部成功，但尚无正式 Reviewer approval，`mergeStateStatus=BLOCKED`。
- 本地最终补修提交：`064bad82d356077c9c9f43a6645040d489b6cbf4`，包含历史适用性门禁、部分店铺失败状态修复、受控 Provider probe 和只读 0061 preflight。该提交尚未推送，因此远端 13 个成功 checks 不能作为此本地提交的 CI 证据。
- 本地补修验证：Ruff format/check PASS；WFS `157 passed, 9 skipped`；全后端 `1783 passed, 127 skipped`；应用导入 PASS；Alembic 单一 head 为 0061。Frontend 未改动，Node 24 单 worker 全量 `60 files / 281 tests`、lint、build PASS。
- 默认门禁与实际执行路径一致：`WFS_AUTO_DETECT_ENABLED=false`、`WFS_AUTO_CASE_CREATE_ENABLED=false`、`WFS_SETTLEMENT_SCOPE_VERIFIED=false`。正式出站还同时要求 interface/config/outbound/real-call 门禁；案件写入还要求 verified collection、唯一身份、完整销量覆盖、已确认标准费、未过期证据和 `verified_wfs`。
- Dry-run preview 不请求 provider、不持久化 detection evidence、不创建或更新案件。正式案件写入仍为 insert-only，冲突时保留既有人工状态。
- Code merge readiness：`READY_FOR_OWNER_REVIEW`。真实 Provider、标准费用、Migration、生产采集、自动检测、自动建案和 Celery schedule 均不是代码合并的隐式授权。

### Provider contract and controlled validation plan

- 仓库官方离线契约 `LX-DB6D62E9EE37` 规定 `sids` 是字符串，取自“查询多平台店铺信息”的 `store_id`；不得把 Walmart 外部店铺号、店名或 `dim_lingxing_stores.sid` 猜作该值。
- `platformLogisticsAmount` 的官方摘要仅称“平台物流费”；同一响应契约另列 `wfsShipmentFee`、`platformWfsStorageAmount` 等 WFS 专用字段。因此非零 `platformLogisticsAmount` 本身不能解除 WFS scope 门禁。
- 后续受控验证限定：`primary`、一个已核对的领星多平台店铺 `store_id`、MSKU `YC00115-1A`、2026-09-01 至 2026-09-30、`length=20`、最多 3 个请求页。若 `total > 60`、店铺/MSKU 不一致、分页不稳定、字段语义不明或出现非销售交易，立即停止。
- 验证只允许记录字段存在性、类型、分页计数、脱敏聚合和错误码；不得输出凭据、完整响应、订单号或商品明细。Database writes、RAW writes、case writes 均为 0。
- 当前状态：`REAL_API_TEST_EXECUTED=NO`，`WFS_SCOPE_STATUS=UNVERIFIED`。

Owner 后续单独批准真实只读验证后，才可在受控环境注入 secret refs 并执行以下固定范围命令；本次未执行：

```bash
cd backend
WFS_PROBE_ALLOW_READ=YES \
WFS_PROBE_SOURCE_ACCOUNT_REF=primary \
WFS_PROBE_STORE_ID=110704872940532224 \
WFS_PROBE_MSKU=YC00115-1A \
WFS_PROBE_START_DATE=2026-09-01 \
WFS_PROBE_END_DATE=2026-09-30 \
WFS_PROBE_PAGE_SIZE=20 \
WFS_PROBE_MAX_PAGES=3 \
LINGXING_ENABLE_REAL_CALLS=true \
LINGXING_ENABLE_TOKEN_REQUESTS=true \
uv run python scripts/wfs_settlement_probe.py
```

脚本硬限制上述账号/店铺/MSKU/日期/分页，先做 dry-run contract 检查；只输出计数、字段存在性和安全错误码，不写数据库、RAW 或案件。

### Product Management standard fee decision

- 已知 $6.55 来自当前 Product Management 代码公式：1000g 与 36.5×20.5×17cm 形成 6lb 向上取整计费重，`$4.15 + $0.40 × 6 = $6.55`。重量与包装尺寸来自当前 Lingxing SKU product-info projection，不是结算订单历史快照。
- `ACTIVE_RULE_COUNT=0` 时使用 `sku-pricing-defaults-v1`，来源为 `product_management_default_unconfirmed`，必须继续阻断自动建案。
- 当前有效 `ProductPricingRuleVersion` 按 `source_account_ref + effective period` 读取；没有 SKU/Item/store 级 WFS override。标准读取器明确标记 `historical_applicability=current_only`，因此 Owner 还必须决定当前尺寸/公式能否应用于目标历史窗口；不能把当前标准直接写成历史事实或确认索赔额。
- Owner 决策记录至少包含：`rule_key`、`rule_version`、`source_account_ref`、`store_scope`、`item_scope`、`effective_from`、`effective_to`、`standard_fee_source`、尺寸/重量证据版本、历史适用策略、`approved_by`、`approved_at`。本 PR 不创建该记录。

### Migration 0061 production plan

| Stage | Required action | Stop condition / recovery |
|---|---|---|
| PRECHECK | 核对生产当前 revision 为 `0060`、0061 单一 head、目标表/索引存在性、表大小、活动长事务、锁等待、重复索引键与磁盘余量 | revision/schema 不符、重复冲突、长事务或容量不足即停止 |
| BACKUP_VERIFICATION | 使用受控机制生成一致性备份，校验文件并在隔离 PostgreSQL 完成恢复演练 | 无可恢复证据即禁止迁移 |
| LOCK_RISK_ASSESSMENT | `DROP/CREATE INDEX uq_gov_sync_work_offset`、普通 `CREATE INDEX`、外键校验和多个 `ALTER TABLE` 都可能持锁或扫描；选择低峰窗口并设置受控 lock/statement timeout | 无法取得锁或预计超出窗口时让事务失败并停止，不手工拆改 schema |
| MIGRATION_EXECUTION_PLAN | 单独授权后从已合并 main 的固定 release 执行一次 `alembic upgrade 20261026_0061_wfs_fee_detection_evidence`；所有功能开关保持关闭 | 非预期 SQL、锁等待、错误或 revision 不一致即停止 |
| POST_MIGRATION_VALIDATION | 核对 revision、约束、索引、两张新表为空、服务 import/health；不采集、不建案 | 任一结构或健康检查失败则停止发布 |
| ROLLBACK_PLAN | 在新 collection/evidence 仍为空时可使用已验证 downgrade；一旦新表有数据，downgrade 会 fail closed，只能保留 schema、关闭功能并走单独的数据保全/前向修复方案 | 不得删除证据或强制降级 |

当前 `BACKUP_READY=NO`，`ROLLBACK_READY=CONDITIONAL`，生产 Migration 保持 `PENDING OWNER APPROVAL`。

Owner/DBA 后续批准对目标数据库进行只读预检后，可通过受控 secret injection 执行；本次未连接任何数据库：

```bash
cd backend
WFS_0061_PREFLIGHT_ALLOW_DB_READ=YES uv run python scripts/preflight_wfs_0061.py
```

该脚本仅在 read-only transaction 中检查 revision、schema、表大小估算、重复组、索引、目标锁和长事务；可恢复备份、磁盘容量、迁移窗口和实际 upgrade 仍必须由 Owner/DBA 独立确认。

### Production gates

| Gate | Status | Evidence required before change |
|---|---|---|
| CODE_MERGE_APPROVAL | `PENDING` | 推送本地补修、补修 HEAD CI 全绿及 Owner/Reviewer approval；本 PR 不自动合并 |
| PROVIDER_READ_APPROVAL | `PENDING` | 单店、单 SKU、最多 3 页、零写入的独立授权 |
| WFS_SCOPE_APPROVAL | `BLOCKED` | 官方/真实响应证明确切 WFS 字段、交易类型及非 WFS 排除规则 |
| STANDARD_FEE_APPROVAL | `BLOCKED` | Owner 完成上述规则、范围、有效期和历史适用决策 |
| MIGRATION_APPROVAL | `BLOCKED` | 可恢复备份、锁风险预检和执行窗口 |
| PRODUCTION_COLLECTION_APPROVAL | `BLOCKED` | Provider 与 Migration 门禁均通过；首次仍限单店单 SKU |
| AUTO_DETECTION_APPROVAL | `BLOCKED` | collection、标准、销量、时效、身份及 WFS scope 全部验证 |
| AUTO_CASE_APPROVAL | `BLOCKED` | dry-run 对账通过后单独批准，限定账号/店铺/批次 |
| CELERY_SCHEDULE_APPROVAL | `BLOCKED` | 手工阶段稳定、监控/急停/重试/租约验收后单独批准 |

## Explicitly not implemented in production

- 未调用真实 Lingxing、未请求真实 Token、未连接或修改生产数据库。
- 未执行生产 migration、未启用调度、未创建生产案件、未部署或重启。

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
- 案件主体仍为 insert-only；每次新的 verified collection 可追加独立检测证据，历史人工字段、跟进、审批、归档、索赔和追回状态不被自动覆盖。
- 0061 在隔离 PostgreSQL 16 上完成带历史合成事实/人工案件的 0060→0061、案件并发/回滚测试、0061→0060→0061。生产索引重建仍存在锁风险，需单独低峰变更计划和生产授权。

## Performance record

- 标准费用批量读取：100 个身份固定 3 次 `execute` + 2 次 `scalars`；销量与覆盖证明固定 3 次查询；结算事实每批为 1 次 Listing 身份查询 + 1 次批量 upsert。
- 合成纯计算基线（本机、非生产）：1 店/100 SKU 为 collection `1.88 ms`、detection `15.61 ms`、峰值 `0.31 MiB`；9 店/1,000 SKU 为 `18.56 ms`、`164.09 ms`、`2.90 MiB`；20 店/10,000 SKU 为 `241.77 ms`、`1804.87 ms`、`28.98 MiB`。
- 上述是合成 parser/detection 资源基线，不是数据库或真实 provider SLA；生产容量仍需受控观测。

## Explicitly not implemented in production

- 未调用真实 Lingxing、未请求真实 Token、未连接或修改生产数据库。
- 未执行生产 migration、未启用调度、未创建生产案件、未部署或重启。

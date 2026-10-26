# PRP: WFS 费用异常自动检测 V1

- Status: Approved for implementation
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

## Explicitly not implemented in production

- 未调用真实 Lingxing、未请求真实 Token、未连接或修改生产数据库。
- 未执行生产 migration、未启用调度、未创建生产案件、未部署或重启。

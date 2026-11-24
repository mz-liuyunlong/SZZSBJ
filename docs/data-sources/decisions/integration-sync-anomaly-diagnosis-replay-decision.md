# Integration Sync Anomaly Diagnosis / Replay 数据源决策

日期：2026-11-20
状态：READY_FOR_PRP（沿用已批准来源；财务人工覆盖及锁账回补仍为 BLOCKED_BY_OWNER_DECISION）
目标：现有异常中心只读诊断、审核留痕、已核实的单日回放及复验；不改变 SaleStat 和送样的业务权威顺序

## 来源及写入责任

| 字段或数据集 | 数据来源 | 业务权威 | 数据层 | 读写边界 |
|---|---|---|---|---|
| 异常身份、状态、人工说明及历史 | gov_integration_sync_anomalies / gov_integration_sync_anomaly_audit | 新系统治理 | NEW_SYSTEM_OWNED | 按授权账号读，update/execute 权限写审计，不含原始数据覆盖 |
| 零元未取消来源订单、有效送样和历史规则版本 | fact_walmart_sample_order_items | 领星订单抓取后的样本事实 | REBUILD_SYNC / FACT | 诊断只读；同步任务唯一来源写入 |
| SaleStat 商品日原始销量、订单数、金额 | fact_walmart_sales_item_daily | 领星 SaleStat | REBUILD_SYNC / FACT | 诊断只读，禁止通过异常中心伪造补齐 |
| 商品身份 | dim_walmart_listings | 领星 Listing | REBUILD_SYNC / DIM | 精确 store_id + item_id + trim(msku) + local_sku，唯一映射；不猜 SKU |
| 每日销售及利润计算结果 | mart_daily_sales_item_day | 派生结果，非权威 | REBUILD_SYNC / MART | 只读核对，唯一重建入口为受控既有 Celery 任务 |
| 任务请求、执行状态 | gov_integration_sync_runs | 新系统治理 | NEW_SYSTEM_OWNED | 指定账号单日的 existing backfill，审计执行者和原因 |

## 字段血缘和重要口径

- 业务日：`America/Los_Angeles`，SQL 使用事实表中已归属的 `business_date_utc_minus_7` 和 `business_date_la`；不跨天猜测订单行。
- 送样身份：来源实付0且未取消；财务入账还需要数量、单价及严格商品键。
- 总量：`count(distinct platform_order_no)` 仅用于订单数；`sum(quantity)` 用于件数；金额 `sum(quantity*unit_price_amount)` 作为**参考单价合计**，不代表实际支付。
- SaleStat 保留来源销量和销售额；超过 SaleStat 的送样保留来源身份但不得使净销售额负数或把不可信利润当作有效结果。
- 诊断分别显示零元记录、已核实样本、SaleStat和已发布的每日销售；不可只依据历史异常 JSON 判定“已解决”。
- 广告 SEM/SP 的费用归属和多商品分配仍需要独立权威证据；本次不允许直接覆盖广告事实或自动关闭。
- 人工补充的说明写入治理审计而非来源/FACT。未来可执行的手工字段覆盖必须独立 L10、字段权限、审批和校验。
- 期限：当前实现为防无审批改写历史财务，自动回放只限美国业务日距今不超过30天；更早日期如2026-08-11保持人工待审。
- 异常中心自动复验使用 `integrations:update`；指定日同步使用 `integrations:execute`；两个行为均在授权 source_account_ref 范围。
- 任意重算只创建任务并异步执行，不等于成功；必须等 MART 成功更新且独立检查通过才标记已解决。

## 前置排查

旧页面/API：不适用（原位增强新系统 `SyncTaskAnomalyCenter`）；旧库/cron/人工旧库入口：不适用。新系统来源：existing Integration Sync 的日 FACT/MART，后台通过 Celery 同步；外部 API 重新获取仅通过既有受控任务，不从 route 直接调用。短期策略：只读诊断、提供证据并重试近30日；长期：受审批的人工覆盖层与锁账历史回补。退出条件：正式人工作业台具备独立审核、差额预览、回滚和对账。

## 风险/未授权范围

- 高风险财务源值覆盖、手工商品归属替换、广告 Campaign 花费分摊、历史锁账日回补 **未获本数据源决策授权**，不能实施成“点击修复”。
- 接口为账户级只读 FACT，查询按业务日、店铺、商品限定，不默认读取 RAW 或旧 MySQL，不持有外部密钥。
- 无生产数据库、真实外部API、自动部署或上线操作。

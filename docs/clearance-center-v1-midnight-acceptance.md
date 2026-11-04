# WFS 清货中心 V1：每日评估与预验收控制

本文件仅描述清货中心 V1。**不授权修改生产数据库、不授权自动执行平台清货操作、不自动申请或审批。**

## 每日执行口径

- 本地业务时区：`America/Los_Angeles`（美国太平洋时区，自动支持 PST/PDT）。
- **每日当地 00:00**：Celery Beat 调度 `clearance_center.scheduler_tick`；每 5 分钟检测；若 00:00 的 Tick 因 Beat/Redis 故障错过，会在同一个 LA 自然日恢复，成功评估每个 LA 自然日最多一次。
- 计算日：本地当天 00:00 对 **上一完整 LA 自然日** 向前的 30/14/7 天销售、广告、利润等做评估；**不能把今日不完整销量视作零**。
- 同一日期唯一 `ops_clearance_daily_runs.run_date_la`；有限重试与 PostgreSQL advisory lock 避免重复并发；按 Listing 完整身份存入 `ops_clearance_daily_evaluations`。
- 运行失败不披露半成品：分析列表只使用最近 `succeeded` 的每日快照，状态与质量由 `/data-readiness` 可观察。
- 清货分析、排行榜、统计由 **数据库筛选/分页/聚合**，不用先加载全部 Listing 到内存。
- 主动申请选择器始终查询**最新有效的 WFS 可售库存 >0**，且在提交/审批时再次校验，与每日快照库存互不混用。
- 自动任务只做分析与证据入库，不生成审批单、不操作 Walmart、降价或广告。

## 真实数据质量门槛（保守策略）

1. Listing 身份严格为 `source_account_ref + store_id + item_id`。销售表有多条 MSKU 时先汇总，再与 Listing 合并，不能跨店、跨账号混加。
2. 30 天、最近 7 天、之前 7 天均需要相应日期的源销售记录覆盖，且无未解决分配记录。原始 30 天销售与 Listing MART 的 `gross_sales_qty` 要一致。缺失不当作零；证据不充分不进入自动候选。
3. 零销量高风险需要：真实 30 天窗口中该 Listing 销量为零、上架至少 30 天、近 30 天内至少 21 个**实际采集的 LA 日期** WFS 库存大于零，且当前 WFS 可售大于零。
4. 利润使用已治理的每日销售 MART 和 `cost_status=complete`，不能把缺失采购成本、头程、汇率填成 0；退款不重复从利润里扣一次。
5. 退款以 `after_sales_refund_items` 中 `refund_effective=true` 且 `refund_effective_date` 落入统计窗口的已完成退款为准；售后申请日期 `return_order_at` 不是实际有效退款日期。期间退款率的分子按有效退款日期，分母按相同期间销售日；**这不是同一批订单的 cohort 退款率**。现有系统未证明可直接读取逐日退款同步成功水位，必须把“退款来源完整性未验证”作为独立阻断项，不猜测。
6. WFS 在途/采购字段若缺少可信 Listing 映射，只提醒，不加入自动风险/强制申请限制。

## 只读真实数据审计

验收环境已迁移后，使用有只读 DB 权限的账号执行：

```bash
cd backend
uv run python -m app.modules.clearance_center.audit --source-account YOUR_ACCOUNT
```

程序设置 `SET TRANSACTION READ ONLY`，不会写业务表。输出：当日批次、Listing 覆盖、WFS 时效、销售源 30 天覆盖、源-MART 数量差异、利润成本缺失、退款资料覆盖未证实等。

前端对应接口：`GET /api/products/clearance-center/data-readiness?source_account_ref=...`。

当返回 `blocking_data_quality_codes`，先调查源数据采集状态；**不得通过合成数据、回填零值或改公式抹平**。

## 权限与隔离

- 数据访问受当前 IAM 的 `source_account_ref` 权限范围限制，前端请求里的账号只能缩小范围，不能扩大范围。
- 清货审批使用 `action:products:clearance:review`；WFS 费用审批权限不授予清货审批能力；申请人不能自审。
- 利润/利润率及其推导风险信息采用已有每日销售字段权限；没有利润权限时不得通过金额、风险信号、列表排序或统计推测敏感数据。
- 跨账号同名 `store_id` 也不得混算；人员负责人仅是业务属性，不替代 IAM 数据权限。

## 隔离验收次序

1. Alembic 从实际 `main` 当前 head 升到 `20261104_0073_clearance_daily`；旧版 `0072` 仍是清货申请/审批存储。
2. 验证 `backend/tests/modules/clearance_center/test_daily_schedule.py`：春秋夏令时 UTC 偏移变化，仍在 LA 00:00 执行。
3. 使用一次性 PostgreSQL 测试库运行 `test_clearance_postgresql_integration.py`：完整 Listing 身份、30 天销售/21 天库存、重复请求、审批/驳回、实时 WFS、权限隔离、每日去重和 165 Listing 的 SQL 分页。
4. 浏览器中验收清货分析列表、待核实状态、手动单 Listing 申请、审批工作台，通过/驳回、数量统一与进度更新。任何操作都不产生实际沃尔玛平台动作。
5. 对有权限的真实店铺运行上述**只读审计**，人工抽样与现有销售/退款/库存/财务报表核对；特别记录没有已证实的退款水位的账户。
6. 只有完成所有业务/安全检查后再运行并核对最新提交 CI；原有 CI 成功**不等于真实业务数据准确**。PR 保持 Draft，未授权前不合并或部署。

### 已知外部验收前提

当前开发连接只支持 GitHub 仓库操作，并未连接可查询真实生产/验收 PostgreSQL 的凭据。因此可以交付执行上述真实数据校验的代码与接口，但**不能声称已实际核验生产数据**。这一步必须在获授权的隔离验收环境使用真实只读数据执行并确认。

## 本轮最终验收之前的额外守卫

- 每日分析必须显示**当天 LA 评估成功**的快照。若仅有昨天或更早的成功批次，页面显示 `stale`，不把历史高/中风险候选视为今日结果；运营仍可按最新 WFS 库存进行单 Listing 主动申请。
- 午夜准点启动是目标，Celery Beat 每五分钟检查，任务会在错过当地 00:00 后于当日补跑；`run_date_la` 唯一约束及 PostgreSQL 会话级锁确保成功批次只认一次。
- P1 性能验收新增 **2,500 条 Listing、两个不同 SQL 分页各 100 条**的数据库回归用例；要求不出现 N+1 查询、总数和跨页身份准确、两次分页的 SQL SELECT 总量不超过 4，耗时上限 15 秒。该门槛必须在隔离数据库真实执行验证，不能仅靠源码检查宣称已通过。
- 退款期间口径需验证三个样本：退款申请早于窗口但有效退款日落在窗口内、申请日在窗口内但完成日在窗口外、窗口内尚未完成退款。只有第一类计入期间已完成退款；退款源同步完整性仍需要独立水位证据，缺少水位时保留 `REFUND_SYNC_UNVERIFIED`。
- 真实数据审计必须在**已授权的验收数据库**运行并保存脱敏汇总证据。本开发环境只有 GitHub 文件/CI 访问，不能把隔离合成测试结果当作真实店铺的 30 天销售、退款、利润和 WFS 库存审计结果。
- 本轮遵循业务安排：六项工作集中开发与准备验收，暂不运行最终 CI。先完成每日评估、真实数据审计准备、销量窗口、RBAC、页面闭环和规模性能回归，再统一进行一次最终 CI。

## 每日任务运行观测字段

验收前通过 `GET /api/products/clearance-center/daily-evaluation?source_account_ref=...` 核对：

- `evaluation_status`：`ready` 代表当天 LA 已有成功批次；`stale` 代表只有过往日期成功批次；`not_ready` 代表未产生过成功批次。
- `scheduled_run_status`：当天 LA 执行记录的状态（`missing/running/succeeded/failed`）。
- `scheduled_attempt_count`、`scheduled_started_at`、`scheduled_finished_at`、`scheduled_next_retry_at`、`scheduled_error_code`：为漏跑、失败重试与幂等验收提供证据。
- 运行时间的业务时区是 `America/Los_Angeles`，而接口中的时间戳均为带时区 ISO-8601 格式，不能混用北京或 UTC 日期判断是否漏跑。
- 任务在 LA 当地 00:00 由 Celery Beat 触发，若此刻队列/Beat 不可用，恢复后可在**同一个 LA 自然日**进行补跑；已成功的日期不会重复生成审批单或重复更新风险。
- 对真实店铺的财务、退款和销售历史正确性，仍须执行 `audit.py` 并保留完整的只读审计输出；若 `REFUND_SYNC_COMPLETENESS_UNVERIFIED` 未解决，不得将整体验收标记为最终通过。

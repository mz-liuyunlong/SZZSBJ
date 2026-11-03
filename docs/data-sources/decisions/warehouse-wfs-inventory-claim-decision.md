# 仓库 · 库存索赔（WFS 成本计价流水）数据源决策

- 调查日期：2026-11-03
- 调查人：仓库代码 AI（库存索赔）
- 目标 method/path：领星 POST `/basicOpen/multiplatform/wfs/cost/valuation/detail`（接口键 `LX-8437AD0BCB9E`）→ ODS `ods_lingxing_wfs_cost_valuation_flow`；后续 `/api/warehouse/inventory-claims*`（PR 2）
- 业务用途：库存索赔（丢失、损坏、收货差错、供应商短少、找回）；结算利润 V2 的货本与库存异动（只读 is_current = true）
- 接口总体状态：READY_FOR_PRP
- 是否包含 NEED_OWNER_DECISION：否
- 负责人批准状态：已批准（rocky，2026-11-03：新建流水表、归本 PRP、独立案件表）；首次开启同步与补历史数据另需书面同意
- 关联证据：`features/pmc-wfs-shipment/context/lingxing-wfs-cost-valuation-api.md`；`features/pmc-handover/chapters/21_lingxing_read.md` §2.1.9、§2.1.19；`features/tools/daily_pull/run.py` L846；`daily/20261025`、`daily/20261102` 的 `lingxing/lx_wfs_flow.csv`
- 决策文件路径：docs/data-sources/decisions/warehouse-wfs-inventory-claim-decision.md
- 后续接口 PRP：PRPs/wfs-inventory-claim.md

## 1. 旧系统与来源调查

| 前置调查项 | 证据位置与调查结论 |
|---|---|
| 旧页面 | 不适用：旧系统无库存索赔页；PMC Demo（8088）WFS 页读本地 CSV，不改 |
| 旧 API | 不适用 |
| 旧接口文件位置 | 不适用；PMC 拉数脚本 `features/tools/daily_pull/run.py` L846 |
| 读取表 | 正式系统无 WFS 库存流水表（已核实）；国内仓流水表 `ods_lingxing_domestic_warehouse_statements` 只含惠州仓 16168 且无原因代码 |
| 表写入方 | 新表由本 PRP 的同步任务独占写入 |
| cron / 脚本 / 外部 API | 领星 A5 接口；新同步默认关闭 |
| 人工写库入口 | 无 |
| 外部平台重新获取可能性 | 可以：接口按日期窗口重拉，领星会回改历史，故按窗口整段替换 |
| 少量配置数据可行性 | 不适用（流水量约 18.5 万行 / 6 个月） |
| 短期策略 | REBUILD_SYNC，默认关闭，授权后补 2026-05-01 起历史 |
| 长期策略 | 同上，每日滚动 60 天窗口 |

### 1.1 单表归属（rocky 2026-11-03 决定）

- 同一领星接口全仓库只建一张 ODS 表 `ods_lingxing_wfs_cost_valuation_flow`、一份契约登记（`LX-8437AD0BCB9E`），归库存索赔 PRP 的 PR 1。
- 结算利润 V2 取消 `ods_lingxing_wfs_cost_valuation_lines`，货本和库存异动读本表 is_current = true；其事实表不得用 serial_number 做唯一键，店铺取本表 store_code / store_id。

## 2. 数据集分类表

| 数据集或字段组 | 业务用途 | 当前权威来源 | 分类 | 短期策略 | 长期策略 | 退出条件或切换点 | 需负责人确认 |
|---|---|---|---|---|---|---|---|
| WFS 成本计价流水 | 索赔计算、结算利润货本 / 库存异动 | 领星 A5 | REBUILD_SYNC | 同步默认关闭；授权后补历史 | 每日滚动 60 天 | 不适用 | 是（已批准建表；开启另批） |
| 店铺对照 | 流水行归属系统店铺 | `dim_lingxing_stores` | REBUILD_SYNC（已有） | 入库时对照，对不上标 unmapped | 同左 | 不适用 | 否 |
| 索赔案件 | 开案、跟进、审核 | 新系统 | NEW_SYSTEM_OWNED | PR 2 | 同左 | 不适用 | 否（已批准独立表） |
| Walmart 赔付 | 已赔、差额 | 无可用来源 | 不在本接口范围 | 显示「未接入」 | 待结算通道 | 不适用 | 否 |

## 3. 数据血缘表（主要字段）

| 接口字段 | 数据集 | 源接口 | 原始字段 | 标准字段 | 转换或公式 | 时区 | 币种 | 新鲜度 | 写入方 | 风险与证据 |
|---|---|---|---|---|---|---|---|---|---|---|
| 流水日期 | 流水 | A5 | dateLocal | date_local / business_date | 原值；取日期 | 待探测 | — | 每日 | 同步 | 契约 §6.1 |
| 结算日期 | 流水 | A5 | date1 | settlement_date | 取日期 | 待探测 | — | 每日 | 同步 | 同上 |
| 类型 | 流水 | A5 | businessType | business_type | 原始字符串 | — | — | 每日 | 同步 | §6.4 |
| 件数 | 流水 | A5 | quantity | quantity | 带符号整数 | — | — | 每日 | 同步 | — |
| 成本金额 | 流水 | A5 | purchaseTotalAmount 等 | *_amount numeric(18,4) | 字符串转 Decimal | — | 待探测 → currency_code | 每日 | 同步 | 文档未写币种 |
| 店铺 | 流水 | A5 + dim | sid / sellerName | store_id / store_code / store_mapping_status | 见 PRP §7.2 | — | — | 每日 | 同步 | sid 95.7% 为空 |
| 流水号 | 流水 | A5 | serialNumber | serial_number | 仅追溯，不唯一 | — | — | — | 同步 | PRP §6.3 |
| 应赔件数 | 索赔 | 本表 | — | should | PRP §7.4 公式 | — | — | 读时计算 | — | PR 2 |

## 4. 风险检查清单

- [x] 每个数据集只有一种分类。
- [x] 不存在未解决的 NEED_OWNER_DECISION（待探测项为接口参数含义，首次授权探测确认）。
- [ ] 时区、币种：待探测（首次开启前确认）。
- [x] REBUILD_SYNC 使用 integration、Celery、标准化存储和质量检查，不在 API route 实时拉外部平台。
- [x] 不读取 ARCHIVE_ONLY 数据。
- [x] 不双写；同一接口只有一张 ODS 表。
- [x] 敏感字段已标记（sellerName 含员工姓名，只在 payload_json）。
- [x] 调查未连接真实数据库、未调用真实外部 API、未修改任何数据（只读本地 PMC 文件和代码）。

## 最终建议

- 接口总体状态：READY_FOR_PRP
- 推荐短期策略：PR 1 建表和默认关闭的同步；授权后用 1 天窗口探测，再补历史
- 推荐长期策略：每日滚动 60 天窗口整段替换
- 旧库退出条件：不适用
- 迁移或同步边界：dateType = 0、全店铺、不过滤 businessType；身份键 (raw_request_ref_id, source_item_ordinal)
- 主要风险：领星回改历史；流水号不唯一；接口未进官方 normalized 索引；时区、币种未知
- 待负责人决定：无（首次开启同步须书面同意）
- PRP 必须引用的结论：单表归属（§1.1）；流水号不可做键；整段替换

## 负责人决定

- 决定：批准进入 PRP；新建 `ods_lingxing_wfs_cost_valuation_flow` 归库存索赔 PR 1；新建独立案件表
- 批准人：rocky
- 批准日期：2026-11-03
- 备注：首次开启同步、补历史数据另需书面同意

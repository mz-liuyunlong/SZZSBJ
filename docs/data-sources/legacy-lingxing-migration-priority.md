# 旧系统领星链路迁移优先级

```text
Status: draft_candidate
Decision authority: Project Owner
Implementation authorized: No
```

## 1. 用途与边界

本文件依据旧系统 lineage matrix 和仓库静态复核，对链路安排调查/迁移优先级。优先级不是实现批准；`REBUILD_RAW_FIRST` 也必须经过接口级 Source Decision、Owner 批准的 PRP 和独立实现任务。

动作定义：

| 动作 | 含义 |
|---|---|
| `REBUILD_RAW_FIRST` | 在任何结构化发布前，先为获批来源建设新系统 RAW 留痕。 |
| `REVIEW_LATER` | 保留证据，等待更高优先级基座和业务口径完成。 |
| `DO_NOT_MIGRATE` | 不迁移旧实现；若未来重启必须重新立项。 |
| `NEEDS_OWNER_DECISION` | 证据、权威或风险未解决，阻塞实现。 |

“需要真实 JSON 采样”只表示未来可能需要脱敏、最小、只读样本；本文件不授权采样、接口调用或凭据使用。文件导入链使用文件样本而非 JSON，仍需单独批准。

## 2. P0 — RAW 基座和首批来源候选

| ID | 旧系统数据分类 | 旧接口或来源 | 旧 RAW | 旧 DIM/FACT | 新系统建议动作 | 迁移风险 | 真实 JSON 采样 |
|---|---|---|---|---|---|---|---|
| LX-LINEAGE-001 | 通用基础 RAW | 全部获批领星接口 | `raw_lingxing_api` | 各下游表 | `REBUILD_RAW_FIRST` | 旧 internal-readonly 暴露大 JSON；新系统需严格权限和分页 | 是，须先确定具体接口 |
| LX-LINEAGE-002 | 商品与库存 | `walmart/list` | `raw_lingxing_api` | `dim_store`、`dim_product`、`fact_inventory_daily` | `REBUILD_RAW_FIRST` | 拉取日不等于业务日；商品与库存粒度混合 | 是 |
| LX-LINEAGE-004 | 销售 | `saleStat/pageList` | `raw_lingxing_api` | `fact_sales_daily` | `REBUILD_RAW_FIRST` | `order_count` 旧口径错误；result_type 需分别留痕 | 是 |
| LX-LINEAGE-009 | 店铺与广告主 | seller list、advertiser list | 旧链缺 RAW | `dim_store_config`、`dim_store` | `REBUILD_RAW_FIRST` | 授权状态和历史变更缺审计 | 是 |
| LX-LINEAGE-010 | 商品成本与商品名 | `batchGetProductInfo` | `raw_lingxing_api` | `dim_product_cost_config`、`dim_product` | `REBUILD_RAW_FIRST` | 成本敏感；人工值与来源值的覆盖边界未定 | 是 |
| LX-LINEAGE-019 | 订单结算 WFS 费率 | profit order report | `raw_lingxing_settlement_order` | `dim_product_wfs_fee_auto` | `REBUILD_RAW_FIRST` | 费率是带样本门槛的估计值，不是来源直接真值 | 是 |
| LX-LINEAGE-026 | 利润派生输入基座 | 组合销售、广告、库存、成本、退款等 | 各上游 RAW | `fact_profit_daily` 等 | `NEEDS_OWNER_DECISION` | 只识别输入；构建器缺失且日界、汇率、送样、缺失成本均高风险 | 否，先分别验证上游 |

## 3. P1 — 第二批高价值链路

| ID | 旧系统数据分类 | 旧接口或来源 | 旧 RAW | 旧 DIM/FACT | 新系统建议动作 | 迁移风险 | 真实 JSON 采样 |
|---|---|---|---|---|---|---|---|
| LX-LINEAGE-003 | 商品价格 | `walmart/list` | `raw_lingxing_walmart_listing` | `dim_product` 价格字段 | `REVIEW_LATER` | Buy Box 缺失回退挂牌价，语义混用 | 是 |
| LX-LINEAGE-005 | 广告商品绩效 SP | `reportAdItemSpList` | `raw_lingxing_api` | `fact_ads_product_daily` | `REBUILD_RAW_FIRST` | 与 CSV、SEM、账单可能重复 | 是 |
| LX-LINEAGE-006 | 广告关键词 SP | keyword + item report | `raw_lingxing_api` | `fact_ads_keyword_daily` | `REBUILD_RAW_FIRST` | 关键词花费不能与商品花费直接相加 | 是 |
| LX-LINEAGE-007 | 广告商品绩效 SB/SV | SB/SV item reports | `raw_lingxing_api` | `fact_ads_product_daily` | `REBUILD_RAW_FIRST` | 无 ItemID 归属和类型完整性风险 | 是 |
| LX-LINEAGE-008 | 广告配置快照 | campaign/group/keyword reports | `raw_lingxing_api` | 三类 snapshot FACT 与状态表 | `REVIEW_LATER` | SV 广告组参数错误，快照不完整 | 是 |
| LX-LINEAGE-014 | 本地仓库存 | warehouse + inventory details | 部分 `raw_lingxing_api` | `fact_local_inventory_daily` | `REBUILD_RAW_FIRST` | 仓库列表缺 RAW；SKU 一对多分摊改变来源数 | 是 |
| LX-LINEAGE-015 | 汇率 | `currencyMonth` | `raw_lingxing_api` | `fact_lingxing_fx_rate` | `REBUILD_RAW_FIRST` | 月份选择和兜底规则影响财务口径 | 是 |
| LX-LINEAGE-017 | WFS 货件 | `queryWFSCargoPage` | `raw_lingxing_api` | shipment 头/明细 FACT 与事件 | `REBUILD_RAW_FIRST` | 状态事件补历史可能重复通知 | 是 |
| LX-LINEAGE-020 | 售后退款 | Walmart return order | `raw_walmart_return_order` | `fact_refund_daily` | `REBUILD_RAW_FIRST` | INITIATED/COMPLETED 计入规则待决 | 是 |
| LX-LINEAGE-021 | 账期与对账单 | payout + statement | `raw_lingxing_api` | reconciliation / credit / commission FACT | `NEEDS_OWNER_DECISION` | 财务类别映射、unknown 保留与权威口径需审批 | 是 |

## 4. P2 — 基座稳定后评估

| ID | 旧系统数据分类 | 旧接口或来源 | 旧 RAW | 旧 DIM/FACT | 新系统建议动作 | 迁移风险 | 真实 JSON 采样 |
|---|---|---|---|---|---|---|---|
| LX-LINEAGE-011 | 采购进度 | `purchaseOrderList` | `raw_lingxing_api` | purchase order 头/明细 FACT | `REVIEW_LATER` | 开放采购量字段未确认 | 是 |
| LX-LINEAGE-012 | 采购现金支出 | `purchaseOrderList` | `raw_lingxing_api` | purchase cash 头/明细 FACT | `NEEDS_OWNER_DECISION` | 历史关闭后不更新，涉及财务时间边界 | 是 |
| LX-LINEAGE-013 | 库存批次与成本 | `getBatchDetailList` | `raw_lingxing_api` | `fact_lingxing_batch` | `REVIEW_LATER` | 守恒异常仍入库 | 是 |
| LX-LINEAGE-016 | 头程发货与分摊 | `queryShippingListPage` | `raw_lingxing_api` | shipping 头/分摊 FACT | `NEEDS_OWNER_DECISION` | 匹配歧义、汇率和作废单审计 | 是 |
| LX-LINEAGE-018 | 月度结算利润 | profit MSKU report | `raw_lingxing_api` | `fact_settlement_msku_monthly` | `NEEDS_OWNER_DECISION` | 高风险财务字段尚未实证拆列 | 是 |
| LX-LINEAGE-022 | 渠道订单销量 | marketplace order list | `raw_lingxing_api` | channel sales FACT | `REVIEW_LATER` | 北京时间窗口与 Walmart 业务日冲突 | 是 |
| LX-LINEAGE-023 | 促销折扣与快速销量 | marketplace order list | order item / discount RAW | promo / fast sales FACT | `NEEDS_OWNER_DECISION` | 送样阈值硬编码，快速销量非利润真值 | 是 |
| LX-LINEAGE-024 | TEMU 清货刊登 | TEMU list | `raw_lingxing_api` | `biz_clearance_other_channel` | `REVIEW_LATER` | 非当前 Walmart US 主线且 INSERT IGNORE 导致陈旧 | 是，Owner 先批准平台范围 |
| LX-LINEAGE-027 | WFS 仓储 CSV | Seller Center CSV | `raw_walmart_storage_csv` | storage fee FACT 与日摊 FACT | `REVIEW_LATER` | 异步日摊失败会与原费用状态断裂 | 否；未来需脱敏 CSV 样本 |
| LX-LINEAGE-028 | WFS 入库运输 CSV | Seller Center CSV | `raw_walmart_inbound_csv` | freight allocation FACT | `REVIEW_LATER` | 未匹配金额需余额和重分摊流程 | 否；未来需脱敏 CSV 样本 |
| LX-LINEAGE-029 | 清货目标 XLSX/CSV | 前端文件导入 | 无原文件/行 RAW | `biz_monthly_plan` 等 | `REVIEW_LATER` | 缺原文件、表头和拒绝行审计 | 否；未来需脱敏文件样本 |
| LX-LINEAGE-030 | 其他渠道清货 XLSX/CSV | 前端文件导入 | 无原文件/行 RAW | `biz_clearance_other_channel` | `REVIEW_LATER` | 平台标识关联不稳定 | 否；未来需脱敏文件样本 |
| LX-LINEAGE-031 | 月度规划 XLSX/CSV | 前端文件导入 | 无文件 RAW | `biz_monthly_plan` | `NEEDS_OWNER_DECISION` | 依赖旧利润快照与业务公式 | 否；未来需脱敏文件样本 |
| LX-LINEAGE-033 | SEM 每日报表 CSV | 缺失的交付件路径 | `raw_walmart_sem_csv`（仅矩阵证据） | ads FACT（仅矩阵证据） | `NEEDS_OWNER_DECISION` | 当前 clean source 无法定位实现 | 否；先补代码证据，再批文件样本 |
| LX-LINEAGE-034 | SEM 账单 CSV | 缺失的交付件路径 | `raw_walmart_sem_csv`（仅矩阵证据） | billing FACT（仅矩阵证据） | `NEEDS_OWNER_DECISION` | 当前 clean source 无法定位实现；绩效和账单粒度不同 | 否；先补代码证据，再批文件样本 |
| LX-LINEAGE-035 | Connect 广告发票 PDF | PDF 导入，解析器缺失 | invoice RAW（schema 证据） | invoice head/line/account | `NEEDS_OWNER_DECISION` | 写入器、任务和异常处理缺失 | 否；未来需脱敏 PDF 样本 |

## 5. P3 — 不进入当前主线

| ID | 旧系统数据分类 | 旧接口或来源 | 旧 RAW | 旧 DIM/FACT | 新系统建议动作 | 迁移风险 | 真实 JSON 采样 |
|---|---|---|---|---|---|---|---|
| LX-LINEAGE-025 | AI PMC 直连补货 | 多个领星接口的内存调用 | 无统一 RAW | 飞书任务/台账，非 MySQL 主链 | `NEEDS_OWNER_DECISION` | 运行状态未知，缺输入快照和审计 | 否；若重启需独立 PRP |
| LX-LINEAGE-032 | 自动广告搜索词 CSV | 主导入器/API 缺失 | ads CSV RAW（部分证据） | keyword FACT（重建脚本证据） | `NEEDS_OWNER_DECISION` | 生产入口不完整 | 否；先补实现证据 |
| LX-LINEAGE-036 | 探针与旧脚本 | 探针、测试和候选接口 | 多数无稳定 RAW | 无稳定生产 DIM/FACT | `DO_NOT_MIGRATE` | 调试代码不能作为生产来源 | 否 |

## 6. 阶段门禁

- 当前仅批准文档规划，所有条目均未获真实调用授权。
- 第一批实现前，Owner 必须从 P0 中指定精确 endpoint、店铺范围、采样页数、保留期和 RAW 读取角色。
- 财务、利润、广告、库存、成本和退款链仍需要独立 Source Decision；P0/P1 只代表优先级，不解除风险门禁。
- 任何 `NEEDS_OWNER_DECISION` 或 `NEEDS_EVIDENCE` 项不得进入实现。

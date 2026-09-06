# 旧库表 ↔ 领星 API ↔ 新系统页面数据源映射草稿

本文件是数据源候选映射草稿，不是最终架构批准，也不是已完成结论。它用于 Phase 2A / Phase 2B 数据库只读盘点后逐步更新。

## 使用方法

1. 先只读盘点服务器旧 MySQL，确认表数量、大小、更新时间、写入任务和读取页面。
2. 再对照 `docs/integrations/lingxing-walmart-openapi/normalized/module_mapping.csv`，找出可替代或补充的领星接口。
3. 短期策略优先保证页面可用：能读旧库结果表就先读旧库只读结果。
4. 长期策略再判断哪些数据由新系统重新拉取、重新建模、重新计算。
5. RAW 表默认只作留痕、审计、回放，不新增前端直查能力。
6. 财务字段不得自行推导公式；必须等待旧库口径、结算口径和负责人确认。
7. 时间字段必须标记时区状态；未确认时写“待确认”。

## 草稿语义

- 本文件所有映射默认状态为 `draft_candidate`。
- 本文件中的 API 候选不代表已批准接入。
- 本文件中的短期 / 长期策略是候选判断，不是最终方案。
- 如与 `do-not-use.md` 或 `normalized/deleted_interfaces.csv` 冲突，以禁止清单为准。

## 初始候选映射

| 状态 | 模块 | 页面 | 业务数据 | 旧库表 | 领星 API 候选 | 短期策略 | 长期策略 | 风险 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| draft_candidate | 工作台 | 今日销售 | 今日销售、今日利润、广告花费、退款率 | `fact_sales_daily; fact_profit_daily; fact_ads_product_daily` | 销售/统计相关接口待验证 | 短期读旧库只读结果表 | 长期评估新系统自拉领星日数据并重建 FACT | 中 | 默认首页数据闭环；先不要直接查 RAW。 |
| draft_candidate | 产品 | 产品管理 | 产品基础资料、成本、生命周期、业务状态 | `dim_product; dim_product_cost_config; dim_product_business_state` | 查询本地产品列表/详情、品牌、分类、标签 | 短期读旧库 DIM/BIZ 表 | 长期由新系统自拉产品资料并保留人工状态在新库 | 高 | 人工生命周期和归档状态不能被接口同步覆盖。 |
| draft_candidate | 销售 | 每日销售 | 销售日事实、订单趋势、MSKU/店铺聚合 | `fact_sales_daily; raw_feishu_table(cxec21)` | 销售订单/统计接口待验证 | 短期读旧库 FACT | 长期新系统自拉领星销售明细并生成新 FACT | 中 | 页面不要实时调领星；先保证口径一致。 |
| draft_candidate | 销售 | 订单利润 | 订单利润、毛利、广告占比、亏损 | `fact_profit_daily; raw_feishu_table(order_profit_daily)` | 财务/销售/结算接口候选 | 短期读旧库利润结果表 | 长期在新系统复刻利润口径，写新库 | 高 | 利润口径复杂，不能只靠 API 字段重算。 |
| draft_candidate | 广告 | 广告总览/关键词 | 广告花费、关键词、广告活动快照 | `fact_ads_product_daily; fact_ads_keyword_daily; fact_ads_keyword_snapshot_daily; raw_walmart_ads_csv` | 广告相关接口不完整，SEM 边界需确认 | 短期继续读旧库/CSV 结果 | 长期单独评估 Walmart Connect/CSV/领星可用性 | 高 | SEM、否定词、竞价倍数可能无法通过领星 API 获取。 |
| draft_candidate | 仓库 | 库存明细 | 库存、WFS、库龄、可售库存 | `fact_inventory_daily; fact_storage_fee_daily; event_wfs_fee_case` | 仓库/WFS 接口候选 | 短期读旧库 FACT/EVENT | 长期新系统自拉库存和 WFS 数据 | 中 | 库存口径需区分 WFS、在途、本地仓、可售。 |
| draft_candidate | 售后 | 退款/退货/Case | 退款、退货、客服消息、索赔 | `fact_refund_daily; raw_lingxing_settlement_order; event_*` | 客服/售后/财务候选接口 | 短期读旧库 | 长期按售后模块重新建模 | 中 | 写入 Case/客服动作类接口暂不接。 |
| draft_candidate | 财务 | 结算对账/广告费用 | 结算订单、仓储费、广告账单、返还明细 | `raw_lingxing_settlement_order; fact_settlement_msku_monthly; fact_storage_fee_daily; raw_walmart_connect_invoice` | 财务接口候选 | 短期读旧库结果表 | 长期新系统自拉结算/账单并固化财务口径 | 高 | 财务口径和月结历史必须严格保留。 |
| draft_candidate | 运营 | 运营日志 | 人工运营动作、系统规则信号 | `biz_product_operation_log; biz_product_rule_signal_daily` | API 文档不能替代人工日志 | 短期继续读旧库 BIZ | 长期新系统维护自己的运营日志表 | 高 | 系统看不到的动作必须靠人工日志。 |
| draft_candidate | AI中心 | AI分析/任务 | AI结果、任务、调用日志 | `ai_*; 新系统任务表待建` | 不应由领星 API 提供 | 旧 AI 结果只读参考 | 新系统自己维护 AI 任务和结果 | 中 | 不要写回旧 AI 表。 |

完整可编辑表见 `lingxing-walmart-api-to-system-data-map-draft.csv`。

## 待补证据

- 服务器旧库 information_schema 表清单。
- TOP 大表和最近更新时间。
- 当前页面/API/cron 对表的读写关系。
- API 候选接口真实调用结果。
- 旧表字段与 API 返回字段的映射。
- 财务字段、币种和时区口径。

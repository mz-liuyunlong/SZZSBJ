# 批次看板身份与负责人数据源决策

日期：2026-10-26。接口总体状态：READY_FOR_PRP（方案足以进入 PRP，不代表批准实现或数据库操作）。负责人已提出功能范围，具体契约随 PRP 审查。

## 1. 前置调查

| 调查项 | 证据与结论 |
|---|---|
| 旧页面 | http://170.106.176.172:8088/domestic/ 有 ItemID、GTIN、负责人列，含多 ItemID 和待归属展示 |
| 旧 API / 文件 | old-walmar-flie/features/pmc-domestic-warehouse/drafts/demo-v7.html 与 rules/business-rules.md；旧页面含历史货件推导逻辑，不直接移植 |
| 新页面 / API | DomesticBatchTable.tsx、domesticWarehouseTypes.ts；GET /api/pmc/domestic/inbound-batches 与详情均缺身份/负责人字段 |
| 读取表 | 已发布入库 MART、采购明细与计划 DWD、Listing DIM、当前产品身份/资料 DWD；发布阶段可读取与 DWD 同源版本的计划 ODS 原字段以检验备注歧义 |
| 表写入方 | 原国内仓 publisher、采购同步和 DWD publisher、Listing 与产品资料同步；业务 GET 不改这些来源 |
| cron / 外部 API | 不新增调度或请求；本次不运行真实同步 |
| 人工写库 | 不引入人工填 ItemID；来源缺失/冲突保持明确标记 |
| 外部重新获取 | 由原同步流程另行受控补齐，不在页面实时调用领星 |
| 少量配置 | 不适用；ItemID 和负责人是业务身份，不能硬编码 |
| 短期策略 | 在原入库发布流程物化采购计划归属与 Listing 匹配证据，GET 读取已发布结果；负责人 GET 批量关联当前产品资料 |
| 长期策略 | 延续同一身份规则和来源版本证据，后续若需共享跨模块身份服务另立任务 |

## 2. 分类与血缘

| 字段组 | 分类 | 来源及关联 | 新鲜度/风险 |
|---|---|---|---|
| 入库基础行与数量 | REBUILD_SYNC | 当前 publication 的 mart_domestic_inbound_batch_board；不改变粒度、日期、数量公式 | 保持原覆盖范围与 source_observed_at |
| ItemID | REBUILD_SYNC | 同账号 purchase_order_sns＋SKU → dwd_purchase_order_line_item.plan_sn → dwd_purchase_plan；经 plan.source_ods_id / source_run_id 校验其 ods_lingxing_purchase_plans 原 remark、plan_remark | 发布时快照；单号集合不能证明入库属于某一计划，多个身份只展示关联、不分库存 |
| GTIN / Listing 校验 | REBUILD_SYNC | 同账号＋来源店铺＋SKU＋备注 ItemID 匹配 dim_walmart_listings；使用现有有效状态与履约条件 | 发布时快照，非实时平台有效性承诺 |
| 负责人 | REBUILD_SYNC | 同账号＋SKU，对应 dwd_lingxing_sku_identity_index、dwd_lingxing_sku_product_info_current；保留 provider / identity_id / SKU ID 完整关联 | 当前产品负责人，不代表入库时历史负责人 |

ID 均为字符串，ItemID 保留 11 位，GTIN 保留前导零。UTC 保存证据时间，页面沿用 Asia/Taipei。无金额、汇率字段。

## 3. 归属规则

1. 每个关联采购单必须存在同账号同 SKU 的明细；每条相关明细保留 order_item_id＋plan_sn，不能把同 SKU 其他采购单纳入。
2. plan_sn 必须能找到同账号计划，计划 SKU 与来源 SKU 一致。来源店铺和计划明确店铺不一致标记冲突；未知店铺不自动跨店归属。
3. 计划备注沿用可识别值优先级：remark 可识别时使用 remark，否则使用 plan_remark。字段内优先识别 ITEMID: 后 11 位数字，没有前缀时识别独立 11 位数字；14 位数字不识别。
4. 选中字段内存在多个不同 ItemID 时报告歧义，不使用原 parser 的第一个匹配。多个计划指向同 ItemID 去重；多个计划分别指向不同 ItemID 保留多值并标冲突。
5. 不能直接把采购明细 remark_item_id 当作纯计划来源，因为其可能是采购明细备注兜底。不能读取可能由打包单回填的采购看板最终 ItemID，避免循环归属。
6. 缺采购关联、计划、备注或原计划证据时标 missing/partial，不静默回退 Listing 推导。DWD 解析值与所引用的原计划证据不一致时标冲突。
7. GTIN 只从精确匹配的 Listing 获取。同一身份出现互相冲突的 GTIN 或多条无法消歧的 Listing 时不选第一条；保留 ItemID 和问题代码。缺 Listing / GTIN 不能拿其他商品补齐。
8. 负责人沿用唯一有效产品身份与唯一负责人 UID 规则；同名不同 UID 不合并。缺失与身份/负责人冲突分别展示，不以店铺负责人或采购员代替。

## 4. 来源、缺失与冲突

候选响应契约详见 PRP。每个身份保存关联采购单、明细、计划、原字段名、source_ods_id/run_id、解析规则版本、观察时间和 Listing 版本引用；不回传完整 RAW 或任意备注正文。身份与负责人分别标记 resolved/missing/conflict，身份允许 partial。

旧发布未带身份字段时返回 missing、issue=IDENTITY_NOT_MATERIALIZED，不把缺字段视为完成归属。GET 不回查 ODS 临时补齐。更新采购或 Listing 后须重新发布才更新身份，页面显示这一新鲜度边界。

## 5. 权限与变更边界

沿用 page:pmc:domestic-warehouse-board:view 及 require_source_account_scope。证据与行同账号，负责人选项与行展示口径一致。不扩大到来源账号外的计划、Listing 或产品资料。

无新表、无 Alembic、无旧库在线回退。MART JSON 追加版本化身份字段，不覆盖历史发布。真实本地重新发布与生产发布均是独立数据操作，不能把 PRP 批准视为生产授权。

## 6. 最终建议

进入 PRP，先实现合成数据验证及本页面联调。具体契约和保守的多值/缺失策略由负责人随 PRP 确认；不包含打包审批身份改造、库存拆分和业务状态。

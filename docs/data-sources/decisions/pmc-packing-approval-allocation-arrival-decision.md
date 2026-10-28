# 打包审批 WFS、建议数量与到货数据源决策

- 日期：2026-10-28；接口总体状态：READY_FOR_PRP；无 NEED_OWNER_DECISION。
- 授权：负责人确认第 1、4、5、6 项修改，并明确在当前分支实施。第 2、3 项保留；不扩展历史人工单或 OWS 回填。
- 目标：现有 `/api/pmc/domestic/packing-approval` pending、summary、orders、edit-options、manual 和审批提交契约。

## 前置调查

| 项目 | 证据与结论 |
|---|---|
| 旧页面、API、文件 | 上轮只读分析的 domestic 仓库候选、`old-walmar-flie/features/pmc-domestic-warehouse/drafts/build_from_daily.py`；不接旧运行时 API |
| 当前读取表 | gov_domestic_board_publications、mart_domestic_inbound_batch_board、dim_walmart_listings、dwd_purchase_order_line_item、ods_lingxing_purchase_order_items、ods_lingxing_purchase_plans、dwd_lingxing_sku_product_info_current |
| 写入方 | 原领星同步、采购 DWD 发布器、国内仓发布器、商品资料标准化；审批仅写既有 OPS 分配和 EVT 审计 |
| cron / 外部 API | 沿用现有同步，本轮不创建任务、不执行真实采集 |
| 人工写库 | 无；数量经既有审批接口输入、权限校验、库存锁和快照审计 |
| 平台重取 | 现有同步可重取；业务 GET 不实时调用平台 |
| 配置替代 | 数量及归属是事实，不能用人工配置伪造 |
| 短期策略 | 新 PostgreSQL 中有界查询和内存投影；成功运行 ODS 选最新业务版本；不读 RAW |
| 长期策略 | 可迁移为版本化发布投影；本轮不新增身份版本表 |

## 数据集与公式（均为 REBUILD_SYNC）

- WFS：DIM 当前目标 Listing 必须 PUBLISHED、fulfillment_type=1；0 保留候选并标 WFS_NOT_CONVERTED。选择同账号同 SKU 全店铺目标时也只返回 1，提交再次校验。
- ItemID：复用批次解析器，保留采购备注+Listing 规则和 blocked 展示。
- 到货（2026-10-28 字段纠错，负责人已明确授权修复）：采购 DWD 按账号+采购单+原明细 ID 去重，与成功同步 ODS 同键关联。已到取同一采购明细 payload_json.quantity_entry（到货入库量），未到取该明细 quantity_receive（待到货量）；分别汇总，不再用 quantity_receive 当已到或差值代替源未到。依据 normalized/response_fields.csv 的 LX-D332F931885E 明细字段及旧 build_from_daily.py 第339行。原 purchase parser 已保存完整 raw_line 到 ODS payload_json，无需新增物理字段。缺失、布尔、负数或非整数保留未知，不推算补值、不累加重复快照、不使用订单头或库存代替。状态须有完整计数；矛盾的“已到未足但待到为0”等组合保留 unknown。
- 比例：采购 DWD 行关联 plan_sn，再读取同账号、同 SKU、店铺匹配的采购计划备注和 quantity_plan；计划备注在本店 Listing 验证后恰有一个 ItemID 才可作为比例证据。一个计划跨采购明细时按 DWD allocation quantity 分摊权重；不重复计整份计划。任何计划身份歧义、数量缺失或候选缺权重时多 ItemID 不预填，不等分猜测。
- 箱规：商品当前标准资料 box_pcs（账号+SKU 唯一、正整数）为建议取整单位；缺失/冲突按件数建议并明确提示。按最大余数法分整箱，剩余不足一箱标为尾差，不强塞。人工仍可改，最终受原库存上限约束。
- 已审批身份的分配扣除后再计算建议，不能把已审批份额重新给剩余身份。blocked 身份仍参与比例，不能把其份额默默转给其他身份。
- 分批：从当前 published MART 全余额范围按账号+仓+采购单+SKU 识别不同入库单，跨店重复行去重；按到仓日期、单号排序。两张及以上为已观测分批；一张且采购已到齐为非分批；历史覆盖不足时标 unknown。此标记只表示当前发布范围，不声称完整领星历史。

无物理表、字段、索引或迁移变更。新增响应字段留存于既有订单 JSON 审批快照，旧快照通过默认值兼容。GET 已会读取采购 ODS 备注，本轮修正原“GET 不访问 ODS”过时说明。新鲜度受现有同步和发布约束。

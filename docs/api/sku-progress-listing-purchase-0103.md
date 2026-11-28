# 新品管理 Listing 独立首批采购 API（0103，实施候选）

现有 GET `/api/new-products/sku-progress/list`、`/summary`、`/facets` 和 POST `/purchase` 路径不变。现有账号范围、权限、分页（SKU）、排序、日期、关键词及响应 envelope 不变。不新增接口或外部调用。`list.items[].listings[]` 增加 `plan_label`（已提交/未提交/待确认）、`proc_label`（采购中/国内未到货/已采购/待确认）、`domestic_shipping_status`（null，来源未确认）。SKU 顶层聚合字段为兼容旧消费者保留，不能用于 Listing 行。`plan`、`proc` 选项使用组内 Listing 实际值，仍按 SKU 去重；同维度 OR、跨维度 AND、保留全部组内 Listing 的原语义不变。无 Listing 时，已核实且无历史记录显示未提交，否则待确认。`ship` 待确认计数原样保留。

POST 请求字段不变：source_account_ref、sku_identity_id、store_id、item_id、quantity（严格整数20）。按账号+SKU身份+店铺+Item ID 独立校验、防重、持久化 claim。保留原 store 级事务锁作为旧记录保护；不再用旧 store 级唯一约束阻止同店不同 Listing。只有同 Listing 已提交且未取消才返回原回执；历史 item_id 未核实时，同 SKU/店铺全部阻塞，错误 SKU_PURCHASE_LEGACY_UNRESOLVED；不自动重试未知回执。原有权限、等级/风险、人工测评、SID/GTIN、已有申请、真实调用开关和签名校验全部保留。真实采购 POST 仍先持久化 intent，再发送。

PMC 采购进度来源 dws_purchase_board：精确匹配本次领星计划号、账号、店铺、SKU、Item ID；不能用其他 Listing 的计划或收货状态推断。无匹配、未知证据或同计划 Item ID 冲突时返回待确认。不将采购完成推断为国内发货。真实数据验收和完整 CI 尚未执行。

### 0103 读取兼容修复（2026-11-28）
列表、统计、筛选从现有采购记录的 JSON 表示读取可选 item_id；旧结构缺字段时视为历史归属未知，不把同店采购复制到多个 Listing。现有无采购记录的已核实 Listing 仍显示未提交。采购候选查询同时校验 0102 字段、两个唯一索引及身份约束是否存在；提交入口在任何真实调用或持久化前执行相同保护，不满足时返回 SKU_PURCHASE_SCHEMA_NOT_READY。保留 0103 迁移，不执行迁移，不新增接口；实际数据库及页面验收待执行。

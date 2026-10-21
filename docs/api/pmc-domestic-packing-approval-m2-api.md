# 打包审批M2接口补充

2026-10-21，当前dev，本地127.0.0.1:55432/szzsbj_dev。最终范围是手工添加打包单与审批前同SKU商品身份修改；系统打包单管理已按负责人要求删除。没有生产访问、提交、推送或部署。

流程：先选择当前批次看板的入库单×SKU，再选择同账号同SKU的有效Listing目标店铺/ItemID；GTIN/MSKU跟随Listing，不能自由修改SKU。填写数量、报关、收货仓备注和原因后，仅保存待审批申请，不发PK、不分配库存。通过审批时重新核对当前来源和Listing指纹、库存上限，并在单事务中发PK、分配原来源库存和写不可变审计；驳回需要原因。多个手工申请共用原入库库存池，可分批审批但不可超量。

跨店铺以当前批次看板入库单为依据，保存原始和目标快照，不要求不存在的领星审批/转移单，不修改领星库存归属。缺少报关信息默认不报关并标记default；人工选择标记manual。未知到货数量保持未知。全部审批仍受local-only/is_test保护，不创建领星OWS或调用WFS。

手工新增需独立packing-manual-create动作权限；页面只读权限不能提交。既有approve/reject动作和来源账号隔离继续生效，不自动授予角色或用户权限。

前缀 /api/pmc/domestic/packing-approval，复用标准success/data/error/meta/request_id响应。

|方法/路径|用途/参数|权限与校验|
|---|---|---|
|GET /manual/sources|入库单×SKU来源，keyword/page/page_size及既有PackingQuery筛选|页面读+来源账号；当前发布惠州仓；余额含本地分配扣减|
|GET /manual/{board_id}/options|source_account_ref，返回来源指纹与同SKUListing身份及listing_version|页面读+来源账号；不跨账号|
|POST /manual|source_account_ref、warehouse_id=16168、board_id、source_version、target_store_id、target_item_id、listing_version、qty、customs、rwh、reason、idempotency_key|manual-create+local guard；同SKU/当前有效Listing/可用量/原因；响应id和pending|
|GET /pending/{candidate_id}/edit-options|source_account_ref，读取候选与目标身份|适用于自动候选或手工申请|
|GET /pending、/pending/summary|沿用现有列表及统计，追加origin=manual待审行|手工来源变化时阻断，成功审批后退出待审|
|POST /pending/{candidate_id}/approve、/reject|沿用既有命令，approve扩展目标店铺/ItemID、listing_version、edit_reason|独立approve/reject；单事务幂等、并发库存、审计|

其余历史及事件接口保持。/packs及/orders/{id}/link、/void、/test-flag已删除。来源、Listing、库存或状态变化返回冲突而非假成功。完整原接口契约见pmc-domestic-packing-approval-api.md；具体模型以packing_schemas.py为准。

本轮本地历史：0051已执行，保留其迁移历史；0052接0051，已在全库备份并检查pg_restore目录后仅应用本地。0052确认OWS关联表为空后删除，停用3条系统管理动作定义；新增ops_domestic_packing_manual_requests，保存来源复合外键、来源/目标快照、数量、报关、备注、原因、操作者、请求JSON/哈希、账号幂等键和UTC提交时间。原发号/审批/分配/事件四表沿用；orders的原快照与最终身份字段用于审批，0051剩余兼容字段不代表存在系统管理功能。

负责人最新要求：后续本地开发不再自动新增或执行迁移编号。本次不增加0053，不回退现有0051/0052。未来结构调整记录SQL及影响；上线前必须单独整理最终生产迁移方案，从生产实际版本验证，不把本地迁移历史直接当作发布批准。当前代码依赖新表/字段，不能只部署代码。现有local-only审批保护也不代表生产写入已开放。

## 2026-10-21 报关与操作列最终调整

下拉仅有“报关”和“不报关”，列表、手工添加、审批弹窗一致，没有可选“默认规则”。初次显示服务端自动结果，未修改时内部命令仍为default，并非前端第三个选项；用户选择后命令declare/skip，结果标记manual，随审批保存，列表暂存不直接写库。

优先产品purchase_remark（当前DWD产品快照所指原始成功响应，按商品ID精确匹配）。字段存在但为空视为无明确备注，默认false；字段不可用时回退同账号同SKU当前DWD所指ODS采购计划/采购明细item_purchase_remark/remark/plan_remark。否定词优先。采购兜底最新明确不报关优先，否则任一历史当前单据明确报关则报关，否则默认false。单据只读取DWD当前版本所指ODS，不能累加同一单据历史旧版本；拆分采购行去重。

既有MART payload新增customs_proof：value(bool)、source(default/product_remark/purchase_remark)、rule(domestic.customs.v1)、field、remark(最多500字)、ref(来源RAW引用或ODS记录UUID)、observed_at。Candidate映射customs_default、customs_default_src与customs_proof，来源证据进入candidate_version；default命令由后端取当前自动结果，人工选择记manual。订单现有customs_value/customs_src及JSON快照/不可变事件保存审批结果，不覆盖历史。旧无证据快照兼容默认false，不追写历史审批。

数据整理在既有发布流程完成，正常业务GET不访问RAW/ODS、不调用领星；CSV不带该新增数据库备注证据，不能声称CSV和本次备注富化字段相同。未改库存、商品身份和到仓日期。

本地备份后重建当前1454行发布版本，其中155行产品采购备注判定报关，1299行默认不报关；旧发布版本保留，MART历史总4362。迁移仍0052，无新表/字段/约束、无0053，历史4审批/3分配/4事件和用户29保留。

操作列“修改”普通按钮、“审批通过”蓝色主按钮、“驳回”普通按钮，统一间距和最小280px列宽（兼容已有窄列设置），权限/业务阻断逻辑不变。当前仅进行本地本模块验证，不进行全局测试；全局回归待用户后续功能全部完成后统一安排。

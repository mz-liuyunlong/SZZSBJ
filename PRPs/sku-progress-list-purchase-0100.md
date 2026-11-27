# SKU 进度列表及首批采购接口（0100）

实施候选；依据负责人已确认的独立汇总、自动更新外部字段、首批采购固定20件且沿用审批工作台限制。尚未部署。

## 数据源决策与边界
- SKU：当前 Lingxing SKU DWD 和当前快照的小批量测品标签；开发时间取0100 ProductList扩展快照。REBUILD_SYNC，消费已有同步结果；同账号SKU不唯一时不做Listing匹配。
- Listing：当前Listing MART，价格按现有 Listing repository 的 monitor current 优先规则（背景刷新仅按已发布的 monitor raw event ID 读取划线价标志，不扫描 RAW），广告状态读取0100 Listing广告状态表；48小时过期显示未知。负责人暂返回 owner_ref，姓名及真实店铺负责人映射待核对。
- 采购：NEW_SYSTEM_OWNED，使用 SKU 首批采购业务表，PMC DWS 按账号、店铺、真实计划单号匹配。S1/S2采购中、S3/S4国内未到货、全部S9已采购；无证据未知。不同来源不得用SKU历史订单猜测。
- 国内发货：NEED_OWNER_DECISION；本次返回 null，不使用打包或采购完成代替发货。独立站只读现有两种维度的业务记录，不推断已提交。
- 读模型仅保存源数据；推进状态、备注、采购及独立站记录在分页查询中批量读取，不自动修改业务记录。删除测品标签只退出汇总，保留业务历史；重新进入复用原身份。
- 更新：production 中启用 SZZSBJ_SKU_PROGRESS_REFRESH_ENABLED=YES 后，每600秒做一次一致快照核对；只写发生变化的行，事务锁避免重叠，不接额外领星API。当前为定时差异核对，不是源事件推送。权限范围沿用新品 scope；采购权限沿用审批工作台管理员或 review 权限。未启用不产生任务。

## API
- GET /api/new-products/sku-progress/list，page/page_size(1..100)，keyword、developer、store、owner、progress、listing、ad、start/end；按SKU分页，返回 items/total/page/page_size/summary，嵌套 listings/purchase_plans/independent_site_submissions。新纳入未操作SKU的 progress_id 可为null，展示默认推进中。无跨店铺数据复制，筛选匹配整个SKU，保留组内Listing。
- POST /api/new-products/sku-progress/purchase：source_account_ref, sku_identity_id, store_id, item_id, 可选 quantity（只允许严格整数20）。每SKU每店铺只提交一次；源端当前标签、唯一SKU、Listing DIM/MART、已确认S/A/B/C、人工测评通过、风险证据通过、原审批工作台 SID/GTIN/Item ID/账号/签名验证。后端真实固定20，数据库 CHECK quantity=20。持久化 claim 后才调用现有签名适配器，未知回执保持阻塞，禁止重发。SZZSBJ_SKU_PROGRESS_PURCHASE_ENABLED=YES 为独立生产启用开关，并继续服从已有 transport gate。不是调用旧审批申请的 decision 路由，也不写旧审批数据。
- API前端正式接线、批量采购、人工推进/独立站写接口、源模块事件增量触发、跨旧审批与新首批采购全局互斥尚未完成。上线前需核对角色、源数据和权限，并验证现有采购门禁不会使首批业务无法执行。

## 验证
新增独立模拟测试及离线 PostgreSQL DDL/DML 检查；真实 PostgreSQL、完整CI及真实领星采购未执行。仅将未部署0100扩为16张表，无其他迁移改动；禁止连接本地/生产数据库或执行迁移。

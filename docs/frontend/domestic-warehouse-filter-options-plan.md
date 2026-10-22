# 国内仓店铺与负责人下拉接入方案

日期：2026-10-19。状态：负责人已确认“同意补齐后端，按当前产品负责人”，进入本地实现；正式数据源决策见 docs/data-sources/decisions/pmc-domestic-filter-options-decision.md，施工记录见 PRPs/pmc-domestic-filter-options.md。

## 目标与复用

国内仓批次看板的店铺与负责人使用真实选项，支持名称搜索、多选、确认、清除和重置，修改条件回到第一页。
复用采购看板、Listing 管理的 ReportFacetSelect；保留 DomesticToolbar 负责展示，Query hook 负责加载，API client 负责请求，types 负责契约。无新 UI 框架、Shared 组件或数据库表。

## 已核实的兼容问题

| 参考能力 | 当前实现证据 | 国内仓限制 |
|---|---|---|
| Listing 店铺选项 | GET /api/listings/walmart/filter-options；data_pages/repository.py 的 listing_filter_options 使用 coalesce(store_name, store_id) 作为 value | 国内仓 store_id 只匹配批次关联表的真实 ID，不能把名称直接传进去；Listing 也只覆盖沃尔玛范围 |
| 采购负责人选项 | GET /api/product-management/options，返回 owners[{uid,name,count}]；purchaseBoardApi.ts 的 getPurchaseBoardOwnerOptions | 国内仓 BatchFilterQuery 尚无 owner_uid；不能仅加载选项就宣称筛选生效 |
| 国内仓店铺筛选 | pmc_domestic/repository.py 的 _clauses/_store_ids；按账号范围关联库存批次 | 可保留重复 store_id 参数，店铺名称需要稳定 ID 映射 |
| 店铺名称来源 | dim_lingxing_stores；采购看板 repository.store_names 已读取该表 | 需处理同 ID 跨账号/平台的名称歧义，禁止按名称反推 ID |
| 产品负责人来源 | dwd_lingxing_sku_identity_index + dwd_lingxing_sku_product_info_current；产品管理 list_owner_options | 需要确认采用当前产品负责人；不能当成采购员、审批人或历史负责人 |

## 推荐实施范围（待确认）

1. 新增国内仓 GET /api/pmc/domestic/filter-options，只读，返回 stores 与 owners，各项为 {value,label}。不返回跨模块统计数量，避免将 Listing 数量当国内仓数量。
2. 店铺 value 是批次关联的真实 store_id；label 来自同账号的 dim_lingxing_stores。优先覆盖可见收货批次关联的全部国内仓店铺，不限定沃尔玛。无法唯一匹配名称时展示 ID，不猜名称。
3. 负责人 value 是 owner_uid，label 是当前产品负责人名称。通过 source_account_ref + SKU 匹配产品身份及当前详情；UID 不按姓名合并。重复身份导致多个负责人时视为待核实，不使用 max 随意指定。
4. 扩展国内仓列表与统计共同的 BatchFilterQuery，接受重复 owner_uid，最多50项；多选 UID 内部为 OR，与店铺、日期、SKU 等条件之间为 AND。
5. 当前负责人缺失/身份歧义的批次保留在未筛选列表；选择负责人时不匹配。到仓日期仍按收货单日期。
6. 新选项接口沿用国内仓现有 read permission 和 source-account scope，不要求用户额外获得 Listing/产品管理页面权限，不放宽权限策略。
7. 前端接入 ReportFacetSelect；加载、空选项、失败与重试明确展示；权限失败不回退硬编码名单。缓存含用户范围，取消过期请求。打包单页面仍保持此前确认的结构范围。

## 数据源调查与门禁

| 项目 | 结论 |
|---|---|
| 旧页面/API/接口文件 | 不读取旧系统；本任务为新系统现有页面增强。参考新系统 frontend/src/pages/products/listingManagementApi.ts、pmc/purchase-board/purchaseBoardApi.ts |
| 读取表 | 候选：dwd_domestic_receipt_batch、dwd_domestic_receipt_batch_link、dim_lingxing_stores、dwd_lingxing_sku_identity_index、dwd_lingxing_sku_product_info_current |
| 写入方 | 国内仓由现有发布任务；店铺由 integration_sync/data_pages_real_sync.py；产品身份和详情由既有 SKU 详情同步链路。此任务不修改这些写入方 |
| cron/脚本/外部API | 无新增、执行或修改；页面只读取已落库结果 |
| 人工写库 | 不新增入口，不改负责人主数据 |
| 外部重新获取 | 已有店铺及产品详情同步能力；不在页面请求时拉领星 |
| 少量配置 | 不适用，店铺和负责人是业务主数据，不能手填固定名单代替 |
| 短期/长期 | 复用既有 DIM/DWD；国内仓 BFF 保持统一消费契约，无旧库运行依赖 |
| 新表/迁移 | 不需要 |
| 必须确认 | 是否允许补齐上述后端接口和参数；负责人是否按当前产品负责人 |

调查时曾为 BLOCKED_BY_OWNER_DECISION；负责人现已确认新增后端范围及当前产品负责人语义。正式决策状态 READY_FOR_PRP，无 NEED_OWNER_DECISION。本文保留原调查与确认方案，最终契约以正式决策、PRP及API文档为准。

## 可执行步骤与验收

1. 确认后端范围及负责人语义，完成正式数据源决策和接口 PRP 审批。
2. 增加只读选项契约及查询；列表/统计共享负责人筛选逻辑，保持不重复计数。
3. 前端封装选项请求和 hook，替换手输店铺 ID/禁用负责人；多选超50项提示，筛选/重置回第一页。
4. pytest 验证权限、账号隔离、名称歧义、同名不同UID、SKU歧义、空负责人、条件交集和统计一致；Vitest 验证 ID/UID 序列化及错误；Playwright 拦截 API 验证两种选项、确认多选、分页重置、失败重试和原页面回归。
5. 更新 API 文档、Data Interface Registry、SOP、交接及页面依赖；运行类型检查、ESLint 和构建，保持 testing 直至真实环境联合验收。

## 风险与回滚

仅回滚本功能明确文件和接口增量，不撤销工作区现有其他修改。不连接生产库、不执行同步/迁移、不改 .env、不部署、不提交推送。后端同目录当前有既有未提交工作，实施时必须基于最新契约增量修改。

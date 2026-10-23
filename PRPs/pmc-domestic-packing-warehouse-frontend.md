# 国内仓打包单（仓库）前端 PRP

日期：2026-10-19；状态：用户确认范围的页面结构已实现并通过本地验收（仅结构，不做示例交互）；页面保持testing。
继承用户直接在dev开发的授权，不新建分支，不提交、不推送，保留已有文件改动。

## 1. Goal
参考用户截图和旧项目业务逻辑，在现有国内仓页面启用“打包单（仓库）”页签，实现表格、筛选与分页结构。不实现装箱弹窗或业务交互。

## 2. Why
让仓库按已审批PK核对商品、填写装箱和确认完成；新页面必须区分前端交互验收与真实业务持久化。

## 3. Scope
纯前端结构：店铺/状态/关键字/审批日期筛选、重置、分页、排序、表格和禁用操作入口。状态、关键字、日期、列宽及页大小仅保留界面设置；店铺选项无来源时禁用。
后端未提供打包接口，因此默认显示“服务未接入”和空表，不从收货批次伪造已审批打包单。
用户最终选择：只做页面结构，不做示例交互。开发/生产均无示例订单、预览入口或模拟保存；业务表格始终为空，待后续批准的接口接入。
不实现审批、OWS创建/写回、领星产品资料/箱规写回、Walmart货件/箱唛和数据库。

## 4. Navigation / Page
沿用/pmc/domestic-warehouse-board，不新增导航或独立后台。页内启用packing；其他未开发页签继续禁用，状态保持testing。
切换页签保留各自筛选和分页；打包页不额外请求批次列表来凑数据。

## 5. Permissions
真实保存/完成/标签服务必须由未来后端校验动作权限和数据范围；本次不新增权限key，不凭用户姓名授权。
缺少真实接口时不显示“业务已保存/已完成”成功提示，也不允许任何内存模拟业务操作。

## 6. Data Source
只读参考old-walmar-flie/features/pmc-domestic-warehouse/drafts/demo-v7.html的PackSheet及review_server/server.py的校验；不复制旧架构、不import旧项目、不调用其服务或读取真实业务快照。
当前backend/app/modules/pmc_domestic仅提供收货批次查询，没有packing业务接口。本任务不新造后端endpoint。
仅定义前端显示类型，没有API客户端、adapter或请求。未来真实接入须有批准的业务数据源决策和API契约。
本页验收没有合成打包单；只模拟登录和原批次看板空响应，不接触业务库存。

## 7. API Contract
本次不新增或修改后端API，不调用虚构路径。
候选前端边界：查询已审批打包单、保存装箱、完成、获取产品标签PDF。未来契约至少含稳定ID、PK、单据来源、审批版本/时间、收货日期、SKU/店铺/ItemID/GTIN、审批数量、装箱版本及操作能力。
真实写请求须expected_version/幂等键；标签返回受权限保护的PDF，不能把普通网页或文字当PDF。

## 8. UI Requirements / Component Reuse Plan
页面职责：组合。页面专属：PackingWarehousePanel、PackingWarehouseToolbar、PackingWarehouseTable；界面状态复用usePageStateCache，类型独立；无装箱Editor或新业务Hook。
复用PageShell/MainLayout、ReportTableShell/ProTable、CommittedSearch、ResetButton、ReportFacetSelect、ResizableColumnTitle、WalmartItemLink/CopyableTextCell、Ant Form/List/InputNumber/Modal/Alert/Popconfirm。
主要列：审批日期、打包单、到仓日期、入库单、采购单、SKU/产品、店铺、ItemID/MSKU、GTIN、产品标签、操作；补充数量、状态和装箱摘要。固定操作区，表格内部滚动，复用采购分页和样式。
默认待打包；切换已打包待发/全部；审批日期范围和关键字仅在提交时查询/过滤，变更后第一页。系统PK与领星人工未关联单区别展示，不给人工单伪造PK。
到仓日期取收货单实际日期；合并多收货批次保留各来源日期，不以最早日期冒充全部；未知不回退入库日期。
装箱弹窗、箱规、差异校验、完成状态和超时计算不在本次实现；此前已确认的“差异原因后允许完成、不强制重审”保留为未来业务约束，本次不模拟。
标签按钮缺ItemID/MSKU/GTIN或标签服务时禁用并解释；不把产品GTIN标签当WFS箱唛。尚无PDF服务，本轮不宣称可下载真实标签。
Loading/Empty/Error/无权限/未接入分别处理；不使用旧项目固定姓名+口令。

## 9. SOP / API Docs
扩充静态国内仓帮助，说明仅页面结构、界面设置不执行查询、无单据与写操作、标签服务缺口。组件复用与验收写任务交接。
没有真实API，不宣称OpenAPI/后端注册完成；接口候选边界写前端设计文档供后续接入。

## 10. Implementation Plan
1. 已按用户选择确认：仅页面结构。
2. 启用现有页签，在packing子目录实现面板、工具栏、表格；不重构共享组件。
3. 定义显示类型与空态，筛选和分页只保留界面设置，不建立假API客户端。
4. 批次查询Hook增加enabled边界，打包页激活时不触发批次查询；回到批次保持原有功能。
5. 更新SOP/交接，运行TypeScript/ESLint、相关Vitest及结构Playwright；无打包样例数据。
allowlist：frontend/src/pages/pmc/domestic-warehouse/**、相关独立e2e、frontend/public/help/domestic-warehouse.html、本文及本任务docs；不修改其他现有工作区改动。

## 11. Validation Gates
浏览器覆盖页签、默认待打包、搜索/状态界面设置、排序/分页/重置、禁用动作、表头、批次回归；验证直接打开打包页没有任何业务API请求。
不做箱规/差异/完成业务测试，因为本次没有这些实现。无真实账号/Token/数据库，无示例入口或打包业务数据。

## 12. Forbidden Actions
不编辑backend/.env/依赖/锁文件/旧项目，不连接数据库或真实外部API，不创造假保存成功，不迁移历史，不部署、不提交推送。

## 13. Rollback Plan
撤销本任务packing目录及页签接入，恢复先前批次面板，保留此前已完成的批次功能和所有其他未提交文件。不清理整个工作区。

## 14. Acceptance Checklist
- [x] PRP范围按用户选择确认为仅页面结构
- [x] 截图主要列和采购看板搜索/分页模式一致
- [x] 到仓日期列以收货单日期为未来接入约束，不回退入库日期
- [x] 无真实后端时为空态，开发/生产均无预览或业务模拟
- [x] 目标检查、浏览器结构和批次回归通过
- [x] SOP和交接完整；保持testing，不宣称真实仓库业务上线

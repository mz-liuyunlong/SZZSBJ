# 国内仓店铺与当前负责人筛选 PRP

状态：按负责人2026-10-19对已审阅方案的明确确认执行；本文固化该方案，不扩大范围。主执行角色：全栈工程实施（本任务一个国内仓模块）。允许项目内 backend-module-designer、react-component-architect 辅助分层，不启用外部部署 Skill。

## 1. Goal / Why
将批次看板手输店铺ID及禁用负责人替换为真实选项和有效服务端筛选，避免名称误传ID。
需求原文及INITIAL_FEATURE要素见 docs/frontend/domestic-warehouse-filter-options-plan.md；用户确认补齐后端并按当前产品负责人。

## 2. Scope / Navigation
只修改国内仓选项和批次列表/统计筛选及其文档、登记、测试；路径 /pmc/domestic-warehouse-board 保持 testing。打包、审批、对账、其他模块及已有他人修改不扩大。

## 3. Permissions / Data Source
不新增permissionKey，沿用 pmc:domestic-batch:read、页面权限策略及可信source_account_ref范围；不额外依赖Listing权限。
数据源决策：docs/data-sources/decisions/pmc-domestic-filter-options-decision.md，READY_FOR_PRP，无NEED_OWNER_DECISION，负责人已确认。读取现有DWD/DIM，完整字段、血缘、歧义和历史口径限制见决策文件。无新表/迁移/外部调用。

## 4. API Contract
GET /api/pmc/domestic/filter-options，无查询参数，response_model为统一SuccessEnvelope；data={stores:[{value,label}],owners:[{value,label}]}。错误401/403/422/500沿用统一错误码、request_id，meta.source=new_system_postgresql，source_objects完整列明，freshness_at未知保持null。
列表和统计共同新增owner_uid重复query参数，最多50项；同字段OR，不同字段AND。空列表不限制，空白UID拒绝。沿用store_id，不把店铺名作ID；不修改到仓日期。模糊产品身份不匹配负责人，不重复计数。

## 5. Architecture / Component Reuse Plan
Route校验权限和envelope；Schema定义选项及参数；Service组合只读结果；Repository负责账号内DWD/DIM查询及共享owner子查询。Model/Migration/Integration/Celery无变化。
页面组合新增选项hook；DomesticToolbar通过props接收结果；复用ReportFacetSelect、已有backendRequest/useQuery、PageShell，不新增Shared组件和依赖。选项缓存key含用户范围，打包页不加载；显示loading/empty/error及重试；多选/重置回第一页。

## 6. Implementation / Validation
数据源→本文→本地计划→后端options及owner过滤→前端选项hook/下拉→pytest（权限/账号/歧义/交集/统计一致/OpenAPI）→Vitest（参数/契约）→Playwright（选项/多选/错误/分页/重置）→TypeScript/ESLint/ruff/构建→SOP/API文档/登记/交接。
官方文档核对SQLAlchemy2 Select/group_by/having及FastAPI Query Parameter Models；AntD/Query沿用已验证项目API。

## 7. Acceptance / Rollback
名称可搜索且提交稳定ID/UID，列表统计过滤一致；未知归属不猜；无越权与业务写入；合成测试通过。API在OpenAPI和现有数据中心API目录可发现；静态帮助及交接更新。不宣称已部署或ready。
按本切片增量撤销，不删除现有表或他人改动；不改.env/生产/部署；继续用户授权的dev分支，不提交推送。

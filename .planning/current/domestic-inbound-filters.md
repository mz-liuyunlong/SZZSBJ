# 国内仓下拉衔接记录

## 2026-10-20 入库批次下拉衔接验收

用户本轮明确要求店铺/负责人/状态调用接口，随后确认截图六状态，并明确“没有，按交接文档补做后端数据方案”。店铺/当前负责人增量已实现；状态数据建设仍是候选方案，未建表/同步，不得宣称六种业务状态筛选已经可用。沿用 dev，不建新分支、不提交推送，保留既有打包和刷新UI调整。

- API：GET /api/pmc/domestic/inbound-batches/filter-options；warehouse_id重复<=50；stores/owners真实稳定ID和UID，options覆盖当前版本所有行，不受当前页影响。旧收货filter-options保持原契约。
- list/summary：owner_uid重复<=50，按当前产品负责人，account+SKU唯一active身份；EXISTS，不复制数量。共享filter_sources.py保留原收货逻辑。meta追加DIM/DWD依赖，不冒充来源同时快照。
- 前端：feature API/hook/类型、DomesticToolbar复用ReportFacetSelect；搜索、多选确认/清除、应用回第一页，loading、独立error/retry；缓存含用户和仓库；打包页不加载选项，切回批次后才加载。六状态从接口返回disabled/reason，下拉可展开查看，不能提交伪业务状态筛选。
- 文档：数据源决策、PRP、API、数据中心目录、registry、SOP/help、前端说明已更新。状态方案 PRPs/pmc-domestic-business-status.md 逐表写明候选变更/影响；旧版SP接口被项目标DO_NOT_USE、出库关联/FIFO边界、分母/历史覆盖需确认；不从零库存或OWS默认箱规猜状态。

实际验证：国内仓pytest **38 passed, 3 skipped, 1 warning**（无独立PG配置的3项迁移演练测试跳过，本轮未接真实PG）；Vitest两文件 **9 passed**；Edge Playwright批次+打包 **6 passed**，最终状态展开可见增补用例 **1 passed**；tsc --noEmit、scoped ESLint、Ruff和git diff --check通过。用例覆盖账号隔离、仓库、旧发布、第一页外选项、同名UID、身份歧义、店铺名冲突、列表统计交集、路由权限/422和失败重试。测试全合成，不依赖生产/真实领星。

本地匿名探测：localhost:5173/api/pmc/domestic/inbound-batches/filter-options 与列表均 **401**，没有此前404；这仅说明匿名访问的鉴权结果，不证明登录态真实数据验证完成。尚需在用户已登录页面核对真实选项/筛选。未重启任何用户后端或生产服务。

安全边界：本轮无DB连接/写入、无schema/migration变更、无.env/密钥变更、无领星真实调用、无权限模型变化、无旧系统修改、无提交/推送/部署。只读参考旧业务文档，未复制旧架构。项目内 backend-module-designer/react-component-architect 辅助；未用外部部署Skill。

命令：backend .venv/Scripts/python.exe -m pytest tests/modules/pmc_domestic -q --disable-warnings -p no:cacheprovider（basetemp在任务artifact目录）；frontend vitest run domesticWarehouseApi.test.ts domesticInboundPreview.test.ts；tsc --noEmit -p tsconfig.app.json；scoped ESLint/Ruff；PLAYWRIGHT_CHANNEL=msedge playwright test e2e/domestic-warehouse.spec.ts e2e/domestic-packing-structure.spec.ts。官方核对 SQLAlchemy2 Select.exists/group_by/having（docs.sqlalchemy.org/en/20/core/selectable.html）及 AntD Select（ant.design/components/select/）；沿用已安装API，无依赖升级。

下一步：用户登录态核对新选项与list/summary；状态数据方案确认后，先解决SP契约禁用和归属/分母，再独立实施数据基础，不能未经批准执行候选新表或真实同步。

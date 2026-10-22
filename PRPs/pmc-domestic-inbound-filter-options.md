# 国内仓入库批次选项衔接 PRP

状态：按本次明确实施指令与此前已批准当前负责人筛选范围执行。用户要求 dev 保留现有改动，不创建分支/PR，不提交推送。只影响国内仓模块。

数据源：docs/data-sources/decisions/pmc-domestic-inbound-filter-options-decision.md，READY_FOR_PRP。新增 filter-options 属原入库 API 模块的选项衔接；原收货 filter-options 保持不变。契约/源对象/字段限制见该决策。

后端：Route 权限/envelope；Schema 验证 options 仓库与 list/summary owner_uid；Service 拼能力和meta；Repository 从当前版本查询选项，owner 用 EXISTS；把已有当前负责人子查询提到 filter_sources.py，旧代码委托复用。Model/Migration/Integration/Celery 不变。

Component Reuse Plan：页面组合 list/summary/options hooks、分页重置与错误；DomesticToolbar 复用 ReportFacetSelect（搜索、多选确认/清除），状态复用现有 AntD Select，六项 disabled 并说明缺业务源。API 封装 backendRequest；类型 feature 文件；缓存含用户范围和仓库；打包页不请求批次选项。loading用占位，失败用 Alert+独立重试，空值保持空选项，不用当前页拼出假的全量名单。不新增共享组件/依赖。

验证：pytest 合成 SQLite 覆盖当前版本/账号/仓库/身份歧义/同名UID/店铺冲突与全量名单/列表统计交集；FastAPI 401/403/422、静态路由顺序和OpenAPI；Vitest序列化；Playwright 点击多选确认、分页重置、重置筛选、失败重试、六项不可用。tsc/eslint/ruff、git diff --check；API文档、数据中心目录、SOP、registry、handoff同增量更新。SQLAlchemy2 EXISTS/group_by/having 和 AntD Select 用法核对官方文档，无第三方API或依赖变更。

回滚：只撤销本增量文件/改动，旧收货 API 不变。无数据库写入/迁移，无密钥和.env变更，无外部业务调用，无部署/重启。状态方案单独审批后实现。


## 实际验收

38项国内仓pytest通过、3项因独立PG配置缺失跳过；9项Vitest通过、6项Edge E2E通过，最终状态下拉实际展开可见用例再通过1项。tsc、scoped ESLint、Ruff、diff check通过。两个本地新地址匿名均401，登录态真实选项尚待用户核对。无生产连接/变更。详见docs/delivery/pmc-domestic-inbound-verification.md最新记录。

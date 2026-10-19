# 国内仓批次看板前端实施记录

日期：2026-10-19。范围：单个前端页面、只读 API 客户端、测试和 SOP。
用户已明确要求直接在 dev 开发，不创建分支；该例外仅覆盖本前端任务，不包含提交、推送、生产操作或覆盖其他任务文件。

## Component Reuse Plan

页面负责组合筛选、统计、表格、详情，不承载网络请求。页面专属组件位于 frontend/src/pages/pmc/domestic-warehouse/components。

| 区域 | 复用组件 | 实施方式 |
|---|---|---|
| 布局 | MainLayout、PageShell | 复用现有路由、导航和页头动作出口，不复制截图顶层菜单 |
| 搜索 | CommittedSearch、ConnectedSearch、ReportFacetSelect、ResetButton | 与采购看板相同的提交搜索及重置模式，仅发送后端已支持字段 |
| 统计 | ManagementStatCards | 保留截图八卡布局；不支持的指标明确待接入，不从当前页推算全局统计 |
| 表格 | ReportTableShell、ProTable、ResizableColumnTitle、CopyableTextCell | 固定分页、内部滚动、列宽、列设置复用现有实现 |
| 列设置 | RuntimeColumnConfigDrawer、userPreferenceCache | 配置按用户保存在本浏览器，不新增偏好接口 |
| 查询 | backendRequest、TanStack Query | 列表/统计/追溯分别封装，取消过期请求，查询key含用户范围 |
| 页面状态 | usePageStateCache、EmptyState、Ant Alert/Spin | 查询条件、分页及统计显隐保留在既有页面缓存，无新状态框架 |
| 帮助 | PageShell headerActions、独立静态SOP | 新标签打开 /help/domestic-warehouse.html |

首版未修改Shared。后续按用户截图调整筛选栏时，为ConnectedSearch/CommittedSearch增加可选searchButtonText及batchPlacement，默认行为保持不变；已补共享测试并更新组件目录。不导入旧系统代码。

## API 边界

静态对照本工作区 backend/app/modules/pmc_domestic/router.py、schemas.py，只消费 GET /api/pmc/domestic/batches、/batches/summary、/batches/{id}/trace。
不修改后端、不创建新接口、不声称这些工作区接口已经部署上线。本模块后端同名目录在任务开始时已存在未提交修改，保留原状。

列表使用 page/page_size/sort，筛选只发送 warehouse_id、store_id、mapping_status、received_from/to、search。IDs按重复query键传递。
每页20/50/100/200，默认50；筛选或排序变化回第一页。契约支持sku/purchase_order_sn/receipt_order_sn多值字段，接入精确和批量搜索（上限50），入库使用既有search综合匹配；ItemID/GTIN/MSKU仍未接入。负责人筛选接入见末节，行内负责人展示尚缺字段。
详情使用trace返回的完整批次，避免从列表猜测出库事件；出库来源未发布时显示未知。

到仓日期只展示 received_business_date，由收货单 receive_time标准化；缺失显示待核实，不能回退为入库日期。件数0与未知分开。
统计的“收货批次”是收货明细行数，不等于在库入库单数。均值、装箱、发货、ItemID、负责人等未提供数据时显示“—/待接入”。
打包页签已提供独立的仓库页面结构，详情见 domestic-packing-warehouse-structure.md；审批、对账页签禁用，通知设置本期不做；不提供写入和导出。

## 权限与状态

导航保留现有权限策略，真实数据读取仍由后端pmc:domestic-batch:read与来源范围控制。未改权限模型。
页面状态testing，不标ready；生产数据正确性、实际后端部署和完整业务权限链需后续联合验收。
403、服务未就绪、校验失败、网络错误有明确提示并可重试；不会将接口错误当成功空列表。

## 官方文档核对

Ant Design 5.29.3： https://5x.ant.design/components/table/ 、 https://5x.ant.design/components/tabs/ 。核对受控分页、排序回调和禁用页签。
TanStack Query v5： https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation 。查询函数将AbortSignal传递给统一客户端。
以本地依赖类型编译核验当前安装API，没有升级或新增依赖。未使用Context7；使用官方文档替代。

## 测试与回滚

客户端契约测试覆盖重复ID、收货日期筛选、严格统计参数、分页、取消signal、未知日期/零数量和权限错误。
Playwright采用合成收货数据，拦截全部/api请求；覆盖路由、分页、提交搜索、重置、显隐统计、更多筛选、列设置、详情及新标签帮助。
没有生产账号、真实Token、数据库或领星/Walmart调用。浏览器截图为合成验收数据。
回滚只撤销本任务页面文件、路由接入、导航testing状态、相关测试与静态帮助；不动既有.gitignore、后端、两份表设计或他人文档改动。

## 待联合验收

后端部署/真实来源新鲜度、完整数据权限、负责人/Listing资料及出库装箱等后续字段；本页不能被当作完整国内仓写业务已上线。

## 截图筛选区调整（2026-10-19）

第一行按店铺、负责人、业务状态、类型搜索（批量入口在搜索按钮前）、到仓日期、更多筛选排列；第二行保留重置、统计显隐，右侧列设置和禁用的导出入口。窄屏允许换行。
业务状态选项为在库、待打包（领星打包单）、已打包待发、超时未发、已发出、非发货出库。当前后端没有这些业务状态字段；选择后暂停查询、清空旧结果并显示待接入提示，清除状态后恢复，避免将未筛选结果当作筛选结果。库存关联状态和排序移入更多筛选。
SKU、采购单号、收货单号使用后端精确多值字段，批量去重且最多50项。入库单号使用既有综合匹配；ItemID、GTIN、MSKU尚未接入。店铺与负责人已由下述增量替换为真实下拉。
共享搜索新增可选文字按钮及批量入口位置参数，原消费者默认布局不变。回归覆盖共享组件、采购看板及国内仓客户端；页面保持testing。

## 店铺与当前负责人选项接入（2026-10-19）

用户确认补齐后端，负责人采用当前产品负责人。通过 GET /api/pmc/domestic/filter-options 获取可见批次选项；真实店铺ID和负责人UID作为value，名称为label。复用ReportFacetSelect进行名称搜索、多选确认/清除；每项最多50个，重置清除，条件改变回第一页。选项请求封装于API/hooks，用户范围进入缓存key；打包页不加载，错误提示允许独立重试。
列表和统计发送相同重复owner_uid参数；同字段OR，不同字段AND。无归属/身份歧义不猜；仍保留未筛选原始收货行。选项只覆盖当前账号范围内的可见批次，不从当前页凑名单，不以Listing名称当ID，也不依赖其页面权限。到仓日期不变。
数据源、后端分层、权限、字段和回滚详见正式决策与 PRPs/pmc-domestic-filter-options.md。没有新表、迁移、同步、真实来源请求或业务写操作。数据库验证仅使用合成数据SQLite内存库，真实PostgreSQL部署/性能待联合验收。OpenAPI及数据中心API目录已登记，SOP已更新。

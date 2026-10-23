# 打包单（仓库）页面结构交接

日期：2026-10-19；主执行角色：前端工程师。用户确认“只做页面结构，不做示例交互”，沿用直接在dev开发授权，不建分支、不提交推送。
PRP：PRPs/pmc-domestic-packing-warehouse-frontend.md。

## 实现范围

在现有国内仓看板启用打包单（仓库）页签，新增packing子目录：显示类型、面板、筛选栏、表格和布局CSS。
主要列按截图：审批日期、打包单、到仓日期、入库单、采购单、SKU/产品、店铺、ItemID/MSKU、GTIN、产品标签、操作。
默认待打包；提供已打包待发/全部状态、提交搜索、审批日期、重置、分页和表头排序/列宽的界面结构。设置按当前用户缓存在现有页面缓存中。

## Component Reuse Plan

页面外壳及布局：现有DomesticWarehousePage/PageShell/MainLayout；不新增全局导航。
搜索：CommittedSearch、ResetButton、Ant Select/RangePicker，与批次/采购看板保持一致。
表格：ReportTableShell、ProTable、ResizableColumnTitle；分页20/50/100/200、默认50，固定表头和操作区、内部横向滚动。
单元格：CopyableTextCell、WalmartItemLink。没有新增或修改共享组件，也不直接拼接Walmart URL。
状态：usePageStateCache仅保存筛选、页大小、排序、列宽与当前页签，不保存业务订单/装箱。

## 数据与动作边界

后端只有收货批次接口，打包查询/保存/完成/标签尚不存在。本次没有API客户端或虚构endpoint，不用收货批次伪造已审批PK。
开发和生产都只有明确的未接入提示与空表，无示例订单、示例模式、装箱弹窗、差异模拟或完成切换。
标签PDF、填装箱、打包完成禁用并说明服务未接入。不能把界面筛选或页大小变更当作已经查询了真实订单。
到仓日期显示模型只接受收货来源日期；多个收货日期分别保留，未知不回退为入库日期。
原批次查询Hook增加enabled，直接打开打包页不请求批次接口；回到批次原功能保留。
loading/error/业务权限状态须待真实API契约接入时实现，本次不能以永远成功的mock伪造这些状态。

## 本任务文件

新增：frontend/src/pages/pmc/domestic-warehouse/packing/下5个文件；frontend/e2e/domestic-packing-structure.spec.ts；本文。
修改：DomesticWarehousePage.tsx、domesticWarehouseQueries.ts、静态帮助与本任务PRP。
未编辑backend、数据库、.env、依赖锁文件、旧项目或其他既有工作区改动；没有部署/真实外部API调用。参考项目仅只读查看业务逻辑，不import或复制其架构。

## 验证与回滚

TypeScript与目标ESLint通过；既有Vitest两个文件共6项通过；Playwright结构与批次回归共5项通过。补充底部分页可见性断言后，本页2项再次通过；已查看最终截图。
Vite生产构建通过，仍提示既有主包超过500kB，不在此任务扩大为全站打包优化。
Ant Table在total=0时隐藏分页，核对本地官方包源码后，使用独立Ant Pagination在相同ReportTableShell内保留零数据分页；页面局部CSS将表格和分页纵向排列，固定底部，未修改Shared。
官方文档核对Ant Design 5.29.3受控分页与页大小：https://5x.ant.design/components/pagination/ 。没有安装或升级依赖。
浏览器数据仅为合成登录和批次空响应，没有打包示例订单；直接打包页断言零业务请求，检查所有操作禁用。
回滚仅移除本任务packing目录及页签接入，保留之前批次页面和所有其他改动；不执行reset/clean。
当前页面仍testing，未宣称打包业务已上线。下一步先明确打包API数据源、权限与契约，再另任务接入真实查询和写操作。

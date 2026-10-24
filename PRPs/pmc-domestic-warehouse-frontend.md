# 国内仓批次看板前端 PRP

2026-10-19。用户确认：按截图开发单页，复用采购看板搜索、分页、样式；直接在 dev 开发，不建分支。此范围不包含提交/推送、后端实现或生产操作。

## 1. Goal
实现 /pmc/domestic-warehouse-board 的只读批次页面。

## 2. Why
提供按收货日期追踪批次的查询入口，为后续打包与对账阶段保留位置。

## 3. Scope
筛选、八项统计布局、表格/分页/排序/列配置、批次追溯、帮助和测试。不实现打包/审批/对账写入、导出及通知。

## 4. Navigation / Page
复用 PMC 现有条目和 MainLayout；状态 testing，不标 ready。

## 5. Permissions
复用现有导航权限与后端 pmc:domestic-batch:read；查询统一客户端，不增加新权限模型。

## 6. Data Source
纯前端消费工作区已有 pmc_domestic 的 batches/summary/trace 契约，不新增或改变后端字段公式。到仓日期来自 received_business_date，即收货单实际收货日期；无值不回退。后端部署和数据源批准不属于本 PRP 的结论。

## 7. API Contract
GET /api/pmc/domestic/batches、/batches/summary、/batches/{id}/trace。参数严格按 schemas.py，页大小20/50/100/200；不发送未支持的负责人、ItemID及批量查询字段。

## 8. UI Requirements
按采购看板采用 CommittedSearch、ReportFacetSelect、ReportTableShell/ProTable、ResizableColumnTitle、RuntimeColumnConfigDrawer、ManagementStatCards；完整复用清单见 docs/frontend/domestic-warehouse-page.md。
未提供指标保持未知；打包、审批与对账页签禁用；统计不使用当前页均值冒充整体均值。

## 9. SOP / API Docs
静态帮助 frontend/public/help/domestic-warehouse.html 新标签打开；API客户端边界和字段缺口记入页面实施记录，不冒充新后端API完成。

## 10. Implementation Plan
类型/客户端及Query hooks→筛选、统计、表格、详情组件→页面组合/导航路由→SOP→契约测试和浏览器验收。
允许修改 frontend/src/pages/pmc/domestic-warehouse/**、路由/现有导航本页条目、PMC占位测试、独立E2E与静态帮助、本文及本任务交接。保留原有未提交文件。

## 11. Validation Gates
TypeScript构建、目标ESLint、客户端/导航Vitest、合成数据Playwright；不得使用生产库或真实外部接口。真实运行结果见任务交接。

## 12. Forbidden Actions
不修改旧系统/后端/.env/依赖/锁文件，不覆盖已有改动，不执行迁移/同步，不部署，不提交推送。

## 13. Rollback Plan
按本任务明确文件清单撤销页面及接入；保留其他任务文件。不执行reset/clean，不删除业务数据。

## 14. Acceptance Checklist
页面与采购看板风格一致；到仓日期口径正确；筛选重置分页可用；缺源诚实展示；权限错误可见；SOP可打开；检查真实通过。后端数据完整性及打包/出库后续能力未验收前保持testing。

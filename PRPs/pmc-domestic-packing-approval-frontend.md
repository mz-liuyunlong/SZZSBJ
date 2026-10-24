# 国内仓打包单审批前端 PRP

日期：2026-10-20；状态：按用户截图与旧版 DEMO（http://170.106.176.172:8088/domestic/ 打包单审批页签）实现**页面结构**；页面保持 testing。继承 dev 工作区，不提交推送。

## 1. Goal
在国内仓看板「打包单审批」页签实现筛选、汇总行、表格与手工添加弹窗结构，与打包（仓库）页相同边界：无真实 API、无示例数据、无模拟审批成功。

## 2. Scope
`approval/` 子目录：类型、面板、工具栏、表格、手工添加 Modal、CSS。审批页可请求已有 `filter-options` 仅用于店铺 ReportFacetSelect；不请求审批列表、不 POST 审批。汇总数字占位「—」。

## 3. Forbidden
不建后端、不伪造 PK、不宣称 ready、不连接旧 DEMO 服务。

## 4. Acceptance
页签可切换；列与截图一致；通过/驳回/提交审批禁用；打开审批页不请求 inbound-batches 列表；E2E 结构用例通过。

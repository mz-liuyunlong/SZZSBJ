# 待发货打包单计划

2026-10-23；当前dev_wfs。用户允许保留并接续已有WFS未提交改动，禁止Git版本/分支/提交推送变更，继续现有本地数据库连接。

- [x] 静态核对国内仓装箱模型、接口与待发货页面。
- [x] 完成需求、接口数据源决策和待确认PRP。
- [x] 负责人确认 `PRPs/pmc-wfs-pending-packing.md` 及本地结构/联调写入范围（“确认，开发”）。
- [x] 后端实现与前端功能联调；真实本地读接口、隔离PostgreSQL写流程及浏览器模拟接口验收。
- [x] pytest 10、Vitest 10、Playwright 2；TypeScript、模块lint及Vite build通过（最后增量检查见handoff）。
- [x] API/SOP/registry及handoff。

已知事实：BoxLine已有UUID；BoxSet有version及completed_at；合法T≠Q必须保留；当前页面OWS前置文案不应成为新业务门禁。既有当前计划为其他任务所有，未覆盖。

本阶段终点为真实pending草稿，不包含审批、Walmart、箱唛、外部取消/改数量。本地四表及权限定义已创建，原有记录数及Alembic版本未变；未在public业务表灌测试装箱。当前真实待发货0张、待装箱4张。

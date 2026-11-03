# PMC WFS 第一期（8088 规则，只读）

Status: local_validation_complete_pending_prp_confirmation
Branch: ai/20261103-pmc-wfs-phase1
Base: ab61bd8877856924ae4c7a7f6a407868fbff0e88（pmc/wfs-v2-20261029，#282 的分支）
PRP: `PRPs/pmc-wfs-logistics-group.md`（#298，状态 Draft，待项目负责人确认）
数据源决策: `docs/data-sources/decisions/pmc-wfs-logistics-phase1-decision.md`

> AGENTS.md §11：PRP 未经负责人确认前不得合并。本分支只开 Draft PR，等 #298 确认后再转为可审。

## Plan

- [x] 迁移 0076：文件登记 + 6 张 ODS 表（显式 DDL，与 ORM 对照测试；有数据时拒绝降级）。
- [x] 文件加载：只接受已校验的采集文件，sha256 幂等，不调外部接口，拒绝符号链接目录。
- [x] 看板事实：Walmart 签收 / 逐 Item 收货 / 上架流水、众壹签收、渠道名称。
- [x] 移植 8088 看板规则（`WFS-RULES-20261010`）：到仓链路、可售日、分段、产品维度、异常。
- [x] 异常中心规则引擎：建单 / 刷新 / 系统自动解决 / 只重开系统解决的案件。
- [x] 待发货打包单：打包完成满 3 天仍有箱子未安排到货件标红（阈值第一期固定 3）。
- [x] 页面：货件看板 8088 列、统计卡、筛选、抽屉；待发货标红卡片和筛选。
- [x] 用 2026-11-02 数据本地回放，与 8088 逐条核对。
- [x] 后端 / 前端 / PostgreSQL 隔离测试 / Playwright（模拟接口）本地通过。
- [x] 更新 API 文档、交接文档。
- [ ] #298 PRP 由项目负责人确认。
- [ ] 部署 AI 推送分支、开 Draft PR，远端 CI 通过。
- [ ] 负责人审核合并；生产迁移、数据加载、定时任务另行批准。

## Not in scope

写回 Walmart / 领星（第二期）、WFS 设置页（D 组）、PK↔OWS 对账（不恢复）、物流板块（下一个 PR）、导航 / 路由 / main.py 等共享文件。

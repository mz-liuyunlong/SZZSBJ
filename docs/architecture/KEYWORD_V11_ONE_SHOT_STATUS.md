# Walmart 关键词 V1.1 同一工作树开发与验收状态

基准：2026-10-24，`acceptance/keyword-planning`。本文件记录当前分支实现，不是上线批准、规则发布记录或官方 Walmart 上传授权。旧版 `KEYWORD_V11_FINAL_IMPLEMENTATION.md`、`KEYWORD_V11_FINAL_ACCEPTANCE.md` 是此前中间快照，其未实现清单不代表当前代码。

## 已实现并有本地验证的链路

| 范围 | 当前源码与边界 |
|---|---|
| 25 类主类型 | `semantic_classifier.py` 从确认的商品字段、已批准品牌证据及冻结的人工复核短语归类；`runtime_rules.py` 用原文 §13.2 的优先级只选一个主类型。无证据保持“人工确认词”。逐类合成证据测试不等于任意自然语言均可自动识别。`GET /preflight` 分别报告确认事实自动归类、人工证据归类、未归类待确认数量。 |
| 九级页面承接 | `runtime_rules.page_coverage_for()` 仅对已验证 Walmart 快照中的标题、详情、属性作字面证明；非字面覆盖需要独立复核和页面实际短语，不能由商品事实冒充。九种状态、硬风险和人工证据有独立测试。 |
| 六维、配额 | `runtime_rules.build_evidence()`、`rule_gates.allocate_ads()` 统一后端执行六维证据分、P0/P1/P2、Exact/Broad 与风险阻断，`analysis_execution.py` 冻结结果。市场数据不可比或 D04/D08 未批准时保持空值/待审，不能伪造可投放分数。D04 两个缺失策略可版本化，但只有已发布且独立审批的规则可应用。 |
| Item ID / ASIN | `source_routes.py`、`source_bridge.py` 只接项目现有已验证并已保存的 Decodo 快照；确认 Item 与账户、Listing 和来源一致后冻结商品事实，ASIN 图片顺序/来源另存。无本任务外部凭据的实时采集接口不伪称成功。状态：`CONTRACT_TESTED_NO_CREDENTIAL`，不是 `VERIFIED_REAL_API`。 |
| Excel 与词库 | `workbook_ingestion.py`、`upload_persistence.py` 保留原件、每张表/每行/错误及哈希，标准词库去重、来源事件与市场观测分别记录。`library_routes.py` 提供单 SKU 与跨 SKU 的账户隔离、数据库分页/搜索/筛选、真实总数和幂等人工词。卖家精灵文件导入可用；自动广告搜索词和授权广告报告尚无可信源数据契约/接口授权，不能声称自动采集完成。 |
| 审批 | 0057 新表及 `rule_governance.py` 支持 D01–D08 提交、独立复核、驳回、审计、哈希绑定和锁定发布；用户身份只从服务端认证主体获取。八项目前全部 `pending`；正式发布仍拒绝。 |
| 原有页面 | `KeywordLaunchPage.tsx` 保留四步布局并读取后端来源、冻结分析、历史和五表；`KeywordLibraryPage.tsx` 保留原报表布局并读取后端分页词库与跨 SKU 关联；页内 `KeywordRulesPanel` 后端保存/恢复草稿与历史版本。Zustand 仍用于当前会话的编辑状态和本地预览，不作为正式分析分数或全库总数。原 CSS、导航和路由没有修改。额外的规则路由及替代工作台已移除。Playwright 同时覆盖合成响应回归与临时 PostgreSQL + 真实 FastAPI 的刷新恢复、人工词和下载；未连接生产。 |
| 五表 | `internal_export.py` 从单一冻结 run 导出 `01`–`05` 内部工作簿并校验行关联与公式注入；`official_template.py` 是严格拒绝式官方模板适配层。当前官方模板/店铺授权/规则发布均未核验，`04` 只能是内部预览，禁止宣称可直接上传。 |
| 数据层 | 0055 关键词核心表、0056 本地迁移图合并、0057 规则决策扩展仅在隔离 PostgreSQL 16 验证；未对生产执行 Alembic。 |

## 仍需如实区分的缺口

- `POLICY_DECISION_REQUIRED`：负责人希望改用原有 RBAC 发布权限且不要求 D01–D08 独立业务审批，但现行项目发布控制仍要求独立发布人和八项审批；该例外尚未正式完成，发布门禁保留。此项不阻止草稿保存、词库、历史和内部导出。
- `EXTERNAL_BLOCKED`：当前 Walmart 官方 Bulk 模板及店铺授权、实际 Item/ASIN 外部采集权限、可信广告搜索词/报告数据源合同。缺少它们时官方上传和广告创建继续关闭。
- `IMPLEMENTED_NOT_VERIFIED`：已保存 Decodo 快照的真实运营数据端到端联调、真实账户权限和性能；隔离合成数据库与真实 FastAPI 的通过不等于真实外部 API 或生产环境成功。
- `NOT_IMPLEMENTED`：任意自然语言覆盖全部 25 类的可靠自动语义识别、自动广告搜索词/授权广告报告入库适配。不能用逐类合成复核短语测试或标签枚举替代这两项。

## 质量与安全记录

前端最终验收使用 Node 24.19.0；后端本地虚拟环境为 Python 3.13。117 项跳过主要来自 PMC、身份、订单等需要显式本地/CI 隔离数据库 opt-in 的测试；关键词两项隔离 PostgreSQL 测试已在本任务单独开启并各通过 1 项。

前端 55 个 Vitest 文件、265 项通过；ESLint 和 TypeScript/Vite build 通过；原页面合成响应 Playwright 回归通过。后端全量 `1629 passed, 117 skipped, 1 warning`；隔离 PostgreSQL 16 上真实 FastAPI + 浏览器持久化闭环通过。117 项跳过并非通过。当前分支的 CI 状态以最新 GitHub 检查为准。

本任务无生产数据库、生产迁移、真实同步/广告发布或外部采集调用；未改 `old-system/`、`.env`。工作树的任务前备份文件均保留且不纳入 Git。正式业务状态仍为 **NO-GO**：草稿持久化和内部流程的本地验证不能绕过发布策略或外部授权。

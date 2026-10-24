# Walmart 关键词 V1.1 同一工作树开发与验收状态

基准：2026-10-24，`acceptance/keyword-planning`。本文件记录当前**未提交**工作树的实现，不是上线批准、规则发布记录或官方 Walmart 上传授权。旧版 `KEYWORD_V11_FINAL_IMPLEMENTATION.md`、`KEYWORD_V11_FINAL_ACCEPTANCE.md` 是此前中间快照，其未实现清单不代表当前代码。

## 已实现并有本地验证的链路

| 范围 | 当前源码与边界 |
|---|---|
| 25 类主类型 | `semantic_classifier.py` 从确认的商品字段、已批准品牌证据及冻结的人工复核短语归类；`runtime_rules.py` 用原文 §13.2 的优先级只选一个主类型。无证据保持“人工确认词”。逐类合成证据测试不等于任意自然语言均可自动识别。`GET /preflight` 分别报告确认事实自动归类、人工证据归类、未归类待确认数量。 |
| 九级页面承接 | `runtime_rules.page_coverage_for()` 仅对已验证 Walmart 快照中的标题、详情、属性作字面证明；非字面覆盖需要独立复核和页面实际短语，不能由商品事实冒充。九种状态、硬风险和人工证据有独立测试。 |
| 六维、配额 | `runtime_rules.build_evidence()`、`rule_gates.allocate_ads()` 统一后端执行六维证据分、P0/P1/P2、Exact/Broad 与风险阻断，`analysis_execution.py` 冻结结果。市场数据不可比或 D04/D08 未批准时保持空值/待审，不能伪造可投放分数。D04 两个缺失策略可版本化，但只有已发布且独立审批的规则可应用。 |
| Item ID / ASIN | `source_routes.py`、`source_bridge.py` 只接项目现有已验证并已保存的 Decodo 快照；确认 Item 与账户、Listing 和来源一致后冻结商品事实，ASIN 图片顺序/来源另存。无本任务外部凭据的实时采集接口不伪称成功。状态：`CONTRACT_TESTED_NO_CREDENTIAL`，不是 `VERIFIED_REAL_API`。 |
| Excel 与词库 | `workbook_ingestion.py`、`upload_persistence.py` 保留原件、每张表/每行/错误及哈希，标准词库去重、来源事件与市场观测分别记录。`library_routes.py` 有账户隔离、分页、筛选及幂等人工词。卖家精灵文件导入可用；自动广告搜索词和授权广告报告尚无可信源数据契约/接口授权，不能声称自动采集完成。 |
| 审批 | 0057 新表及 `rule_governance.py` 支持 D01–D08 提交、独立复核、驳回、审计、哈希绑定和锁定发布；用户身份只从服务端认证主体获取。八项目前全部 `pending`；正式发布仍拒绝。 |
| 三个正式页面 | `KeywordLaunchPage.tsx` 默认挂载真实后端控制台；`KeywordRulesPage.tsx`、`KeywordLibraryPage.tsx` 默认从后端查询/提交，刷新可恢复持久结果。旧本地草稿入口有显式警告，不是正式结果。Playwright 对三页的 Mock API 契约、恢复和权限作浏览器验收；未连接生产。 |
| 五表 | `internal_export.py` 从单一冻结 run 导出 `01`–`05` 内部工作簿并校验行关联与公式注入；`official_template.py` 是严格拒绝式官方模板适配层。当前官方模板/店铺授权/规则发布均未核验，`04` 只能是内部预览，禁止宣称可直接上传。 |
| 数据层 | 0055 关键词核心表、0056 本地迁移图合并、0057 规则决策扩展仅在隔离 PostgreSQL 16 验证；未对生产执行 Alembic。 |

## 仍需如实区分的缺口

- `EXTERNAL_BLOCKED`：D01–D08 负责人裁决与独立审批、当前 Walmart 官方 Bulk 模板及店铺授权、实际 Item/ASIN 外部采集权限、可信广告搜索词/报告数据源合同。缺少它们时正式评分、上传和广告创建继续关闭。
- `IMPLEMENTED_NOT_VERIFIED`：已保存 Decodo 快照的真实运营数据端到端联调、真实账户权限及性能、三页面在已批准环境的业务验收；本地合成测试不代表真实 API 成功。
- `NOT_IMPLEMENTED`：任意自然语言覆盖全部 25 类的可靠自动语义识别、自动广告搜索词/授权广告报告入库适配。不能用逐类合成复核短语测试或标签枚举替代这两项。

## 质量与安全记录

前端最终验收使用 Node 24.19.0；后端本地虚拟环境为 Python 3.13。117 项跳过主要来自 PMC、身份、订单等需要显式本地/CI 隔离数据库 opt-in 的测试；关键词两项隔离 PostgreSQL 测试已在本任务单独开启并各通过 1 项。

前端 54 个 Vitest 文件、264 项通过；ESLint 和 TypeScript/Vite build 通过；Playwright 对三页恢复/审批/词库及后端分页共 4 项通过。后端全量 `1622 passed, 117 skipped, 1 warning`；全仓 Ruff check 与关键词模块 Ruff format check 通过；隔离 PostgreSQL 16 的 DDL/约束和 0057/事务专项各 1 项通过。117 项跳过并非通过。全仓 Ruff format check 仍报 7 个已存在的 Decodo/安全入口/冻结迁移文件，未大范围重排他人代码或 SQL。0055 仅对冻结 SQL 字面量设置明示 E501 例外，不改 DDL；0048/0055 仅调整导入顺序。`scripts/check-rule-pack.sh` 因既有规则资料的字面项目名扫描失败；**未**删除原始资料或弱化扫描范围来伪造通过。

本任务无 commit、push、PR、生产数据库、生产迁移、真实同步/广告发布或外部采集调用；未改 `old-system/`、`.env`。工作树有大量任务前既存未提交与备份文件，均保留。总状态：**NO-GO**，不等同于可编程部分尚未开发，也不意味着可以绕过真实审批。

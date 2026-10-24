# Walmart 关键词 V1.1 本地实现清单

> 历史中间快照：本页的未实现清单不再代表当前工作树。请以 [`KEYWORD_V11_ONE_SHOT_STATUS.md`](KEYWORD_V11_ONE_SHOT_STATUS.md) 和最新源码/测试为准；旧记录保留以便追溯。

状态基准：2026-10-24。指定工作树 `acceptance/keyword-planning`，目标是**如实描述现有未提交代码和本轮增量**，而非宣布正式上线。未进行 commit、push、PR、生产迁移、真实广告请求。

## 模块与 API

| 领域 | 现有实现 | 现状 |
|---|---|---|
| 规则底座 | `backend/app/modules/keyword_planning/rule_gates.py`、`runtime_rules.py` | 25 标签白名单/优先级、保守页面证据、分数区间、名额与硬风险门；没有完整语义分类器 |
| Excel 原件 | `workbook_ingestion.py`、`upload_persistence.py`、`analysis_routes.py` | `.xlsx` 安全解析、原件哈希/行保留、本地私有 blob 接口；本轮拒绝 Excel 错误格、畸形坐标与超长单元格，防止静默截断 |
| 分析执行 | `analysis_entrypoint.py`、`analysis_execution.py` | 已存来源核对、幂等运行、账户范围、快照结果；缺失证据仍转人工复核。本轮修正“部分评分即成功”误判 |
| 读取 | `router.py`、`service.py`、`repository.py` | 商品 runs、run、run keywords 三组只读响应 |
| 前置与治理 | `preflight_routes.py`、`analysis_preflight.py`、`governance_routes.py`、`rule_governance.py` | 只读前置检查、规则集/版本查询、禁用规则草稿；发布固定阻断，不能自称审批 |
| 内部工作簿 | `internal_export.py` | 五 Sheet 内部分析文件；04 是预览，不是 Walmart 官方 Bulk 模板 |

API 路由清单（均为 `/api/v1/keyword-planning` 前缀）：`GET /products/{product_id}/runs`、`GET /runs/{run_id}`、`GET /runs/{run_id}/keywords`、`GET /preflight`、`GET /rulesets`、`GET /rulesets/{rule_set_id}/versions`、`POST /rulesets`、`POST /rulesets/{rule_set_id}/drafts`、`POST /rules/{version_id}/retire`、`POST /rules/{version_id}/publish`（固定拒绝）、`POST /imports/xlsx`、`POST /analyses`、`GET /runs/{run_id}/internal-workbook`。写接口受本地显式开关和后端权限限制；前端 UI 不等于安全边界。详情以路由 `response_model`、统一响应契约和专门 API 文档为准；现有文档未达到 `AGENTS.md` §15 的“全部 API 完成”标准。

## 数据层

`20261023_0055_keyword_planning_core.py` 新增 21 张关键词分层表：

- RAW：`raw_kw_upload_file`、`raw_kw_upload_row`、`raw_kw_walmart_page_snapshot`、`raw_kw_asin_snapshot`、`raw_kw_asin_image`。
- 事实/维度：`ai_kw_product_fact_snapshot`、`dim_kw_term`、`biz_sku_keyword`、`biz_kw_market_observation`、`biz_kw_source_event`、`biz_sku_asin_reference`。
- 分析/治理：`ai_kw_rule_set`、`ai_kw_rule_version`、`ai_kw_analysis_run`、`ai_kw_run_file`、`ai_kw_run_asin`、`ai_kw_run_keyword`、`ai_kw_listing_version`、`ai_kw_export_file`、`biz_kw_decision_history`、`ai_kw_rule_evaluation`。

既存未提交的 Decodo `20261022_0048_decodo_config_usage.py` 与 0055 通过 `20261023_0056_merge_decodo_keyword_heads.py` 合为单一 Head。字段、FK、索引、不可变触发器以 [`KEYWORD_SCHEMA_DATA_DICTIONARY.md`](KEYWORD_SCHEMA_DATA_DICTIONARY.md) 为准。隔离 PostgreSQL 16 DDL/事务写入测试通过；**生产未迁移**。隔离迁移 `upgrade → 0056` 通过，向 0054 降级被设计中的 `KW_SCHEMA_DOWNGRADE_REQUIRES_EXPLICIT_BACKUP_AND_APPROVAL` 保护门阻断，不得绕过。

## 25 类、九状态和六维的实际映射

`runtime_rules.TYPE_PRIORITY` 的 25 个优先位如下；`classify_type()` 只在**上游已给出带证据的 `VerifiedLabel`** 时选主类型，并非自动文本分类。`test_runtime_rules.py` 对每个标签都有合成契约用例，不能用该测试代替原文语义黄金样例。

| 优先位 | 已登记标签 | 自动语义识别 |
|---:|---|---|
| 1 | 合规/认证风险词 | 未实现 |
| 2 | 错货架词 | 未实现 |
| 3 | 配件/替换词 | 未实现 |
| 4 | 结构冲突词 | 未实现 |
| 5 | 材质不符词 | 未实现 |
| 6 | 规格/尺寸不符词 | 未实现 |
| 7 | Pack/数量不符词 | 未实现 |
| 8 | 颜色/款式不符词 | 未实现 |
| 9 | 品牌/竞品词 | 未实现 |
| 10 | 机器设备词 | 未实现 |
| 11 | 食材本身词 | 未实现 |
| 12 | 泛流量词 | 未实现 |
| 13 | 核心本体词 | 未实现 |
| 14 | 核心材质长尾词 | 未实现 |
| 15 | 核心规格/数量词 | 未实现 |
| 16 | 核心场景长尾词 | 未实现 |
| 17 | 精准长尾词 | 未实现 |
| 18 | 同义表达词 | 未实现 |
| 19 | 复数变体词 | 未实现 |
| 20 | 拼写变体词 | 未实现 |
| 21 | 相邻结构词 | 未实现 |
| 22 | 相邻用途词 | 未实现 |
| 23 | 次级场景词 | 未实现 |
| 24 | 低价值重复词 | 未实现 |
| 25 | 人工确认词 | 缺少证据时的保守兜底 |

九状态的显示枚举及候选页面分取自 `rule_gates.COVERAGE` / `PAGE_POINTS`：标题已埋词、标题意思已覆盖、详情/属性已埋词、场景/用途能接住、用户确认能接住、页面没埋但可优化、页面埋得弱先验证、页面看不出来、页面不建议埋。`runtime_rules.page_coverage_for()` 对文字命中和带来源人工复核作保守判断；不能自动完成全部页面证据归因。

六维输入位置：`runtime_rules.MATCH_SCORES`、`INTENT_SCORES`、`ROOT_SCORES`，`rule_gates.PAGE_POINTS`，`MarketPoints` 和 `risk_penalty`。`build_evidence()` 只接受可追溯分量；不明数据保持 `None` 并阻断正式分级。分数和判断在 `ai_kw_run_keyword` 保存，`analysis_execution.py` 防止“只部分评分就把整个批次标成功”。D04/D05 尚未批准，不能称六维正式评分完成。

## 前端实际绑定

`frontend/src/pages/ai-center/keyword-launch/KeywordLaunchPage.tsx`、`keyword-rules/KeywordRulesPage.tsx`、`ads/keyword-library/KeywordLibraryPage.tsx` 已有本地 Zustand 工作流，**不是三页完整后端持久化闭环**；页面刷新不能保证从关键词后端恢复全部状态。`frontend/src/features/keyword-planning/components/KeywordV11LiveConsole.tsx` 有真实 API 调用封装，但尚未挂到正式页面。`frontend/src/api/keywordPlanningV11Api.ts` 是可用客户端契约，不能据此宣称页面联调通过。本轮不覆盖原有 UI、不虚构成功数据。

## A–L 交付状态

| 项 | 状态 | 真实边界 |
|---|---|---|
| A Walmart Item ID | NOT_COMPLETED | 现有 Decodo/商品查询组件不等于完整可信 Item ID→确认事实→冻结快照流程；真实授权与数据源决策待定 |
| B Amazon ASIN | NOT_COMPLETED | 多图/历史模型具备，真实 ASIN Adapter、可信来源快照及正式 UI 未闭环 |
| C Excel/词库 | IMPLEMENTED_NOT_VERIFIED | 原件解析与持久化有测试；多来源入库、后台人工词、完整前端词库未闭环 |
| D 25 类 | NOT_COMPLETED | 25 标签/优先级契约和逐标签测试存在；不是证据驱动语义判别器 |
| E 九级承接 | NOT_COMPLETED | 保守证据门/九状态枚举测试存在；缺完整真实页面证据归因 |
| F 六维评分 | NOT_COMPLETED | 后端范围/缺失阻断存在；D04/D05 与证据定量规则待批准 |
| G P0/Exact/Broad | IMPLEMENTED_NOT_VERIFIED | 安全名额与排序规则测试存在；正式执行依赖 D06 和真实证据 |
| H 规则审批 | NOT_COMPLETED | 草稿、只读与退役边界有测试；双人审批/发布证据链未实现，发布默认阻断 |
| I 统一快照 | IMPLEMENTED_NOT_VERIFIED | 持久化执行/幂等测试通过；前端仍有本地计算路径，未统一消费 |
| J 五张 Excel | IMPLEMENTED_NOT_VERIFIED | 内部五 Sheet 测试通过；正式 04 模板未核验、禁用 |
| K 三页联调 | NOT_COMPLETED | 仅本地页面编译与单测，不等于真实后端 E2E |
| L 自动广告扩展 | NOT_COMPLETED | 来源与评估基础模型在 21 表中；任务/审核/执行状态契约未完成；真实执行禁用 |

`EXTERNAL_BLOCKED` 项：原始锁定规则、D01–D08 审批、官方 Walmart 模板、外部凭据与店铺授权、生产上线审批。不能用外部阻断掩盖上表尚未编码的功能。

## 本轮实际增量

在不覆盖现存大量未提交代码的前提下，只做 Excel 拒绝式解析、分析完成状态安全修正、隔离 PostgreSQL 测试 FK 注册修复、Alembic 测试 Head 对齐，以及对应回归测试和状态文档。未补造未经批准的外部 Adapter、官方模板、业务分类黄金规则或新生产迁移。

# Walmart 关键词 V1.1 本地最终验收记录

> 历史中间快照：本页的测试数量及未实现清单不再代表当前工作树。请以 [`KEYWORD_V11_ONE_SHOT_STATUS.md`](KEYWORD_V11_ONE_SHOT_STATUS.md) 和本任务最后一次实测报告为准；旧证据保留以便追溯。

验收基准：2026-10-24；指定 `acceptance/keyword-planning` 工作树。结论：**NO-GO（不满足完整 V1.1 正式上线/广告投放验收）**。此结论不会覆盖已经通过的局部测试；它区分“安全底座可运行”和“业务闭环已完成”。未提交、未推送、未建 PR、未访问生产库、未执行生产迁移。

## 验收矩阵

| 验收项 | 证据 | 结果 |
|---|---|---|
| 25 类逐类 | 25 个标签契约用例；无锁定原文黄金语义样例及自动证据分类器 | 枚举通过，分类 NOT_COMPLETED |
| 九页面状态 | 保守页面判断和错误/缺证据用例 | 显示状态底座通过，完整证据归因 NOT_COMPLETED |
| 六维评分、D04/D05 | 后端范围/缺失阻断测试 | 正式评分 EXTERNAL_BLOCKED + NOT_COMPLETED |
| Exact/Broad 限额与风险 | `rule_gates.py`、`runtime_rules.py` 单测 | 局部 COMPLETED；正式规则发布未授权 |
| Excel 原件及隔离 | 错误格、非法坐标、超长值、原件和 SHA 测试 | 局部 COMPLETED；完整多来源词库 NOT_COMPLETED |
| PostgreSQL 迁移 | 独立 Docker PostgreSQL 16，0056 单 Head；21 表、13 索引、113 约束、3 函数、17 触发器；真实事务写入/幂等通过 | 本地 DDL COMPLETED；生产 EXTERNAL_BLOCKED |
| 五张 Excel | 内部五 Sheet 测试 | 内部预览 COMPLETED；官方 04 NOT_COMPLETED/EXTERNAL_BLOCKED |
| 三个现有前端页面 | TypeScript build、Vitest、ESLint | 静态/单测通过，后端持久化联调 NOT_COMPLETED |
| 真实 Item ID/ASIN | 模型与局部查询/Decodo 代码；无端到端证据 | NOT_COMPLETED；凭据与数据源审批 EXTERNAL_BLOCKED |
| 规则审批 | 草稿/读取/退役保护；publish 固定拒绝 | 双人审批与实际发布 NOT_COMPLETED |
| 权限/安全 | 现有 HTTP 401/403/404/409、账户隔离、PG 约束测试 | 局部 COMPLETED；上线前仍需业务权限验收 |

## 实际测试与检查

以下数字以本轮命令输出为准，不能把 `skipped` 写成通过：

- 后端全套（从 `backend/` 目录执行）：`1581 passed, 117 skipped, 1 warning`。
- 后端关键词/Decodo 初始定向基线：`131 passed, 2 skipped`；随后增量定向用例（含部分评分状态）通过。
- 前端全套串行复验：`53` 个测试文件、`263 passed`；Vite 生产构建与 ESLint 均通过。一次并行复跑曾因非关键词 `App`/`AdsCampaignsPage` 用例超时得到 `259 passed, 4 failed`；这两个文件随后单独串行 `5 passed`，完整串行再验 `263 passed`。构建提示大 chunk，仅是性能警告，不代表端到端业务通过。
- 独立 PostgreSQL 16：关键词 DDL 结构和分析真实写入/幂等测试通过；迁移 `upgrade 0056` 通过；`downgrade 0054` 按设计被 `KW_SCHEMA_DOWNGRADE_REQUIRES_EXPLICIT_BACKUP_AND_APPROVAL` 阻断。不得把保护性阻断写成可自动回滚。
- `git diff --check` 通过。
- 针对整个现有未跟踪关键词模块的 Ruff 全规则检查仍有旧文件的格式/行长告警；本轮未大范围格式化用户已有代码。
- `bash scripts/check-rule-pack.sh` 未通过：它对整个现有未跟踪关键词文档集合中的项目名称作禁止词扫描。现有文档需单独治理；不能通过删除原文“修绿”。

## 实际差异和安全边界

本轮修改现有 `workbook_ingestion.py`、`analysis_execution.py`、相关定向测试及 Alembic scaffold 测试；新增本三份最终状态文档与决策登记索引；对早已在工作树里的数十个本地修改、stash 和 `.bak` 一律保留。`git status` 显示的所有变化**不能全归因于本轮**。没有操作 `old-system/`、`.env`、生产服务、真实广告、正式投放、外部 API 或真实生产数据库。

## 阻断与下一步

1. 负责人核准《接口数据源决策》和正式 PRP，明确 Walmart/ASIN/市场观察的数据源、权限、字段和时效；找到并冻结原始规则以及 25 类黄金样例。
2. 为 D01–D08 建立真实审批记录和不可变审计，落实双人规则发布流程。
3. 获取并验证 Walmart 官方 Bulk 模板版本及店铺授权；正式导出继续禁用。
4. 基于批准契约实现缺失的 API、25 类语义识别、九级证据、三页持久化联调、审批闭环、E2E，逐模块单独测试与审查。
5. 单独治理现有 Ruff/rule-pack 告警并完成变更审查；在获得生产授权前不执行迁移或上线。

结论不能写为 `COMPLETED`；当前只可继续作为本地安全底座开发。

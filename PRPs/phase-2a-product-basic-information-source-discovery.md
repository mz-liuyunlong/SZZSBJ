# Phase 2A：产品管理 / 产品基础信息只读查询 Source Discovery PRP

## 1. Title

Phase 2A：产品管理 / 产品基础信息只读查询 Source Discovery

目标 method/path：

```text
待定——本任务不定义后端接口契约
```

本文件是 Source Discovery PRP，不是后端接口 PRP，也不构成调查或实现授权。

## 2. Status

```text
Status: Approved
Owner Approval Required: Yes
Investigation Execution Allowed: No until owner changes Status to Approved
```

- `Draft` 状态不允许开始调查。
- 负责人批准后，必须将 `Status` 明确改为 `Approved`。
- PRP 存在不等于调查已获授权。
- 本轮工程师不得自行将状态改为 `Approved`。
- 后续调查必须等待负责人另行下发 Source Discovery 执行 Prompt。
- Source Discovery PRP 不等于后端接口 PRP。
- 数据源决策完成也不等于允许编写接口；只有达到门禁要求后，才可另行准备并审批接口 PRP。

## 3. Background

产品基础信息只读查询在进入后端接口 PRP 前，必须先确认候选字段的业务含义、当前读写链路、权威来源、更新方式、短期策略、长期归属、风险和旧库退出条件。当前尚未执行证据调查，也没有形成数据源分类结论或负责人决定。

本 PRP 仅规划一次受控的 Source Discovery，用于后续形成接口数据源决策，不预设旧系统、外部平台或新系统数据库中的任何一方为权威来源。

## 4. Objective

负责人批准本 PRP 并另行下发执行 Prompt 后，按批准范围收集只读证据，回答产品基础身份字段的数据来源问题，并形成唯一主要决策产物：

```text
docs/data-sources/decisions/products-basic-information-query-decision.md
```

该决策文件本轮不得创建。后续调查完成、负责人处理所有必要决定且接口总体状态达到 `READY_FOR_PRP` 后，方可另行准备后端接口 PRP。

## 5. Scope

后续获批调查仅可围绕产品基础身份字段的候选范围规划证据：

- 商品标识。
- SKU / MSKU。
- 产品名称。
- 平台。
- 店铺映射。
- 品牌。
- 分类。
- 基础状态字段。

边界说明：

- 上述内容只是候选调查范围，不是已确认字段清单或分组结论。
- 字段名称、含义和分组不得凭空确定，最终内容必须以后续批准调查取得的证据为准。
- 本任务不定义正式 API method/path。
- 本任务不定义 request schema、response schema 或数据库模型。
- 本任务不定义权限实现、同步实现或前端展示契约。

## 6. Explicit Exclusions

以下业务数据或能力不在本次 Source Discovery 范围内：

- 产品负责人或员工归属。
- 生命周期。
- 手工运营状态。
- 编辑、归档和批量操作。
- 成本、采购价、供货价和 WFS 配送费。
- 库存、销售和利润。
- 广告、结算和退款。
- Listing 写入。
- 外部 API 真实调用。
- 生产数据导出。
- API 实现。
- 数据库模型设计。
- migration。
- 同步任务实现。
- worker 或定时任务实现。
- 权限实现。
- 前端页面修改。
- backend 代码修改。

如后续证据显示旧产品管理页面混入上述数据，只能在决策材料中记录为“关联但不在本次范围”，不得扩大调查或设计范围。

## 7. Agent Assignment

```text
Main Execution Role: Backend Engineer
```

负责人批准本 PRP 并另行下发执行 Prompt 后，主执行角色可在批准边界内使用：

- `engineering-minimal-change-engineer`。
- `engineering-technical-writer`。
- `testing-evidence-collector`。
- `engineering-backend-architect`。
- `engineering-database-optimizer`，仅用于规划并执行批准范围内的静态表结构分析；不得连接数据库、执行 SQL 或调查未批准的实际表结构。

Agent Skill 只是工作模式，不是人员、任务角色或权限主体。任何 Skill 均不得扩大文件范围、绕过 PRP、连接数据库、调用真实 API、部署或授权 Git 写操作。

## 8. Allowed Evidence After Approval

只有负责人将本 PRP 状态改为 `Approved`，并另行下发明确的 Source Discovery 执行 Prompt 后，才可在该 Prompt 的精确范围内读取：

1. `old-system/` 中与产品基础信息直接相关的只读证据：
   - 旧页面引用。
   - 旧 API route。
   - 相关 service。
   - SQL 和表名引用。
   - cron、同步任务和写入链路引用。
2. `docs/integrations/**` 中与 Lingxing/Walmart 产品基础信息相关的离线资料。
3. 仓库已经提交且执行 Prompt 明确允许读取的数据字典、schema 报告和表结构说明。
4. 经负责人另行明确批准的只读数据库表结构信息。

约束：

- PRP 获批不自动授权连接真实数据库。
- 真实数据库检查必须由负责人另行批准精确数据库、表、账号和命令范围。
- 如需真实数据库盘点，必须拆成单独的只读 DB 盘点任务。
- 离线 integrations 文档只是候选证据，不是官方实时验证，也不是已批准接入。
- 后续读取 `old-system/source/**` 必须限定到 PRP 和执行 Prompt 共同批准的相关文件，不得进行无边界全量调查。
- 所有证据读取仍受 `AGENTS.md`、`docs/OLD_SYSTEM_READONLY_RULES.md` 和任务 allowlist 约束。

## 9. Forbidden Operations

即使本 PRP 后续获批，仍持续禁止：

- 修改、格式化或重构 `old-system/**`。
- 执行任何旧系统脚本或安装旧系统依赖。
- 复制旧系统代码到新系统。
- 调用真实 Lingxing、Walmart 或飞书 API。
- 写入生产数据库或修改数据库结构。
- 执行 migration、回填或同步。
- 导出大批量生产数据。
- 读取或输出 secrets。
- 使用 root SSH 或 MySQL root。
- 部署、重启服务或修改 CI、Vercel、服务器及生产配置。
- 编写后端接口。
- 实现正式 API path/schema 或数据库模型。
- 默认双写。
- 把候选来源写成已批准权威来源。

在当前 `Draft` 轮次中还禁止读取 `old-system/**`、`docs/integrations/**`、`.env*`、`secrets/**`、`credentials/**`、依赖或构建产物目录，以及连接数据库、服务器或外部 API。

## 10. Planned Investigation Questions

后续获批调查必须回答：

1. 当前功能在旧系统对应哪个页面？
2. 旧系统是否已有读取接口？
3. 旧接口文件在哪里？
4. 旧接口读取哪些表？
5. 各表由谁写入？
6. 是否由 cron、脚本或外部 API 同步产生？
7. 是否存在人工写库入口？
8. 数据能否从 Lingxing、Walmart 或其他权威来源重新获取？
9. 少量配置数据是否适合由新系统维护？
10. 哪些字段属于基础信息，哪些应排除到其他模块？
11. 短期策略是什么？
12. 长期策略是什么？
13. 旧库退出条件是什么？
14. 哪些结论需要负责人确认？

不能由批准范围内证据确认的问题必须标记为待确认或 `NEED_OWNER_DECISION`，不得用假设补齐。

## 11. Planned Evidence Recording Schema

后续调查至少按以下字段逐项记录：

```text
field_or_dataset
business_meaning
candidate_source_table_or_api
evidence_path
current_writer
current_reader
external_origin
freshness_or_update_chain
confidence_level
short_term_strategy
long_term_strategy
risk_level
owner_decision_needed
notes
```

记录规则：

- `evidence_path` 必须指向仓库文件和行号。
- 已确认事实、静态推断和待确认事项必须明确区分。
- 不得把源码推断写成生产环境事实。
- 不得复制真实生产数据或敏感值作为证据。
- 证据缺失、冲突或超出授权范围时，必须保留不确定性并触发停止条件。

## 12. Data Source Classifications

后续每个数据集或字段组只能选择以下一种分类：

- `READ_LEGACY_TEMPORARILY`。
- `REBUILD_SYNC`。
- `MIGRATE_ONCE`。
- `NEW_SYSTEM_OWNED`。
- `ARCHIVE_ONLY`。
- `NEED_OWNER_DECISION`。

分类规则：

- 本 PRP 不为任何候选字段预先选择分类。
- `NEED_OWNER_DECISION` 是阻塞状态，不是最终策略。
- 存在未解决的 `NEED_OWNER_DECISION` 时，总体状态必须为 `BLOCKED_BY_OWNER_DECISION`。
- 聚合查询不得使用模糊的 `MIXED`。
- 不同来源必须拆成数据集或字段组逐项分类。
- 不得默认双写，也不得保留未定义优先级的多个权威来源。
- `READY_FOR_PRP` 只表示可以准备后端接口 PRP，不表示可以编写接口。

## 13. Expected Investigation Output

批准并完成调查后的唯一主要决策产物为：

```text
docs/data-sources/decisions/products-basic-information-query-decision.md
```

后续决策文件应包含：

- 第 10 节全部调查问题的逐项证据与回答。
- 第 11 节证据记录字段。
- 按数据集或字段组拆分的单一分类。
- 字段血缘、当前读写方和更新链路。
- 短期策略、长期策略、风险和旧库退出条件。
- 需负责人决定的事项和接口总体状态。

本轮不创建该决策文件，不填写调查结论，不作数据源分类结论或负责人决定。只有后续调查完成、负责人处理必要决定且总体状态达到 `READY_FOR_PRP` 后，才能另行准备后端接口 PRP。

## 14. Validation Plan

本轮仅验证 Draft PRP 的文件边界、Markdown 完整性和规则合规性：

```bash
git status --short --untracked-files=all
git diff --check
bash scripts/check-rule-pack.sh
sed -n '1,320p' PRPs/phase-2a-product-basic-information-source-discovery.md
```

验收项：

- [ ] 仅创建 `PRPs/phase-2a-product-basic-information-source-discovery.md`。
- [ ] Markdown 列表和 code fence 完整。
- [ ] `Status` 仍为 `Draft`。
- [ ] `Owner Approval Required` 为 `Yes`。
- [ ] `Investigation Execution Allowed` 为 `No until owner changes Status to Approved`。
- [ ] 未写入调查结论、分类结论或负责人决定。
- [ ] 未读取或修改禁止目录。
- [ ] 未写入真实密钥、连接信息、生产 URL 或生产数据。

本任务是 docs-only，不运行前端或后端测试，不安装依赖，不运行服务。

后续 Source Discovery 的验证方式必须由负责人批准的执行 Prompt 精确限定，且至少检查证据路径与行号、事实/推断/待确认区分、分类唯一性、`NEED_OWNER_DECISION` 阻塞规则和禁止操作合规性。

## 15. Stop Conditions

发生以下任一情况必须立即停止，不得扩大范围或猜测：

- PRP 状态仍为 `Draft`，或负责人未另行下发 Source Discovery 执行 Prompt。
- 执行 Prompt 未精确限定允许读取的旧系统、文档或 schema 文件。
- 需要读取未批准文件、密钥、生产数据或敏感值。
- 需要连接数据库、服务器、SSH tunnel 或真实外部 API，但未取得对应的单独明确授权。
- 证据不足、证据冲突、业务含义或权威归属无法确认。
- 任一数据集或字段组需要负责人决定。
- 调查触及明确排除的业务域，或需要设计接口、schema、模型、migration、同步、权限或前端。
- 目标文件已存在但内容来源不明，或工作区出现无关改动。

证据不足或冲突时，应记录 `NEED_OWNER_DECISION`；只要仍有未解决项，总体状态必须保持 `BLOCKED_BY_OWNER_DECISION`。

## 16. Rollback Boundary

本轮唯一变更是新增本 PRP 文件，不涉及代码、数据库、配置、服务或外部系统。回滚边界仅为由项目负责人决定是否删除该未跟踪文件，或在复审后修改其 Draft 内容；工程师不得执行 Git 暂存、提交、推送、建 PR、合并或删分支。

未来 Source Discovery 也必须是只读调查。若发生越界，应立即停止，保留只读检查结果并报告；不得通过写入、迁移、同步或部署方式“修复”调查问题。

## 17. Owner Approval Checklist

- [ ] 确认本 PRP 的 `Status` 当前为 `Draft`，且 PRP 存在不代表已授权调查。
- [ ] 确认调查对象仅为产品基础身份字段候选范围。
- [ ] 确认 Explicit Exclusions 完整，且关联证据不会扩大范围。
- [ ] 确认目标 method/path 保持“待定——本任务不定义后端接口契约”。
- [ ] 确认未来允许的证据来源和文件范围。
- [ ] 确认 `old-system/source/**` 只能按 PRP 与执行 Prompt 的共同精确范围读取。
- [ ] 确认本 PRP 获批不自动授权真实数据库、服务器、外部 API 或敏感信息访问。
- [ ] 确认真实数据库盘点如有必要将拆为单独只读任务，并单独批准精确范围。
- [ ] 确认数据源分类、阻塞状态和 `READY_FOR_PRP` 含义。
- [ ] 确认唯一主要调查产物路径。
- [ ] 如接受本 PRP，由负责人将 `Status` 明确改为 `Approved`。
- [ ] 批准后由负责人另行下发 Source Discovery 执行 Prompt；在此之前不得开始调查。
- [ ] 确认数据源决策完成不等于允许写接口，后端接口仍需另行编写并批准 PRP。

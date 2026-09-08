# AI 与知识治理策略

> Status: 规则在负责人合并后为 `approved`；AI、知识库、检索与向量能力均为 `planned`。
> Scope: AI 输入、检索、生成、Review、采纳，以及文档/知识资产生命周期。
> Non-goals: 不选择模型、向量库、供应商，不批准真实数据接入或自动写回。

## 硬性规则

1. AI 输出是派生结果，不能自动覆盖业务数据、manual override、canonical、DIM/FACT 或财务口径。
2. 每次 AI 运行必须记录 prompt/template version、model、input source、retrieval source、cost、operator、权限上下文和输出状态。
3. AI 输出必须可追溯到获准输入数据、文档、业务表记录或用户指令；无法追溯时不得作为业务依据。
4. AI 建议被采纳时，必须由人工确认并生成独立 manual override、business event 或 audit；保留建议与采纳动作的关联。
5. SOP/文档必须有版本、状态、权限、owner、`published_at`；Draft、过期或撤回文档不能当正式依据。
6. Search/Vector index 是可重建派生层，不是权威源；删除、权限或版本变化必须传播到索引。
7. 检索结果必须追溯到 `doc_id/chunk_id` 或 `source_table/source_record`，并携带来源版本。
8. AI 不得读取超过调用者权限或 data scope 的数据，不得读取 secret 级字段。

## 受治理实体

| entity | purpose | required_metadata | authority/status |
| --- | --- | --- | --- |
| `ai_run` | 一次模型调用/工作流运行 | run/request ID、operator、purpose、权限/data scope、model、cost、时间、状态 | implemented 前均 planned；输出为 derived |
| `ai_task` | 定义允许的业务用途与输入/输出边界 | owner、permission key、budget、model allowlist、review policy | 必须 approved 后执行 |
| `ai_prompt_template` | 版本化系统/任务 prompt | template version、owner、change reason、approved_at、禁止数据级别 | approved version only |
| `ai_output` | 保存生成结果及 Review 状态 | run ID、content reference、citations、status、reviewer | candidate，人工采纳前非权威 |
| `ai_retrieval_log` | 记录检索查询与实际召回来源 | query hash/text policy、doc/chunk/record refs、ACL result、ranking metadata | audit/lineage evidence |
| `ai_review_feedback` | 记录接受、拒绝、更正与原因 | reviewer、decision、reason、before/after 或 accepted scope | audit evidence |
| `doc_asset` | 文档逻辑身份与 owner/权限 | doc ID、type、owner、ACL、source、current version | 文档权威取决于已发布版本 |
| `doc_version` | 不可变文档版本 | version、hash、status、published_at、supersedes | Draft 不可作为正式依据 |
| `doc_chunk` | 可重建检索片段 | doc/version ID、chunk ID、offset/hash、parser version | derived |
| `knowledge_status` | 生命周期状态 | draft/reviewed/published/deprecated/revoked 等受控枚举 | 仅 `published` 可作正式知识来源 |

## 输入与检索控制

| 阶段 | Required controls | Forbidden patterns |
| --- | --- | --- |
| 登记 AI task | 目的、owner、permission、data scope、预算、模型白名单、留存 | 通用“AI 助手”权限访问全部数据 |
| 准备输入 | 字段敏感级别、最小化、脱敏、来源/version | secret、完整 token、密码、无关 PII 进入 prompt |
| 建索引 | ACL、source/version、chunk/hash、删除传播、可重建 | orphan vector；索引永久绕过来源权限 |
| 检索 | 在检索前执行调用者 permission/data scope；记录实际召回 | 先全量召回再由模型过滤权限 |
| 生成 | prompt/model/version、cost、输入和 citation refs | 无来源事实声明；隐藏模型/成本 |
| Review/采纳 | 人工 reviewer、reason、目标 action、audit | AI 直接写业务表或 override |
| 删除/撤回 | 原文、chunk、vector、cache 和可见引用同步处理 | 只删文档，仍可从向量召回 |

## 文档权威与引用

- `published` 仅说明该文档版本获准作为文档依据，不自动覆盖结构化业务事实。
- 生成回答必须区分：来源直接陈述、确定性转换、模型推断和未知项。
- 引用必须指向用户有权限访问的来源；不能用不可见引用证明可见答案。
- 公司文档/SOP、API 参考和旧系统报告具有不同 authority；`legacy_reference` 不能被模型提升为新系统事实。

## 成本、安全与审计

- AI Token 仅由后端集成配置管理，前端永远不接收完整密钥；日志只留脱敏标识。
- `ai_run` 至少记录模型标识、输入/输出 token 或等价用量、成本、用途模块、operator 和 request ID。
- 敏感/财务/员工数据需字段级授权和明确 AI purpose；无授权即 fail closed。
- prompt injection 内容是不可信输入，不能改变权限、工具、Source Decision 或数据写入边界。

## 示例（非实现）

| 场景 | 正确处理 | status |
| --- | --- | --- |
| AI 总结已发布 SOP | 检索前校验 ACL，答案引用 doc/version/chunk | candidate |
| AI 建议产品标签 | 输出保持 candidate；人工采纳后另写 override/event/audit | candidate |
| 文档撤回 | 标记 revoked 并重建/删除相关 chunk/vector/cache | candidate |

## Forbidden patterns

- AI output 自动写 canonical、DIM、FACT、MART 或 manual override。
- 向量库成为唯一文档副本或业务权威源。
- 使用 Draft SOP、无 owner 文档或未知版本作为正式依据。
- 模型绕过 API permission/data scope 直接读表或 RAW。
- 保存真实 secret、Cookie、Authorization header、密码或私钥到 prompt、日志、文档或索引。
- 无 prompt version、model、input/retrieval source、cost、operator 或 Review 状态的 AI 运行。

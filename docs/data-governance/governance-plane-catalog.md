# 治理平面目录（Governance Plane Catalog）

> 规则状态：仅在负责人 Review 并合并后成为 `approved` 基线。
> 实现状态：除非引用独立证据，控制能力均为 `planned`。
> Scope: 跨数据集、管道、API、文档与 AI 资产的治理控制。
> Non-goals: 不选择产品、数据库、工具或实施顺序。

治理平面不产生新项目角色或额外权限。每个实现 PRP 必须选择适用平面；省略高风险控制必须由负责人明确批准。

`docs/data-sources/database-layering-standard.md` 仍保留早期 G1-G10 简表。本目录的 G0-G18 是扩展目录：既有文档中的旧编号继续按原文名称解释，不得按新编号静默重映射；新 PRP 应同时引用本文件路径、governance code 与完整名称。`owner_role` 表示治理责任，不新增项目执行角色，具体负责人仍由项目负责人指定。

| governance_code | governance_name | purpose | applies_to | required_artifacts | required_controls | examples | forbidden_patterns | owner_role | implementation_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G0 | Source Registry / Source Decision | 决定来源是否接入、是否存 RAW、谁是字段/数据集权威源以及退出条件 | 所有新读取、同步、导入、迁移和业务 API | source registry entry、接口级 Source Decision | source type/status、authority、raw policy、owner、evidence、风险与短/长期策略 | Walmart API 为 `candidate`；旧库临时读为 `legacy_reference` | 无 Source Decision 接入；离线文档当已验证事实 | 项目负责人/数据 owner | planned |
| G1 | Data Ownership / Stewardship | 指定字段、表、指标的业务 owner、技术 steward 与批准责任 | 字段、数据集、表、指标、API | owner/steward matrix、升级路径 | 责任角色、Review 周期、停用/交接责任 | 产品字段由业务 owner 定义，后端维护 contract | “团队负责”；孤儿表；工程师自行决定高风险口径 | 项目负责人 | planned |
| G2 | Ingestion Observability | 证明每次摄取何时、以何输入、多少数据、何结果执行 | API/文件/旧库同步与导入 | run/batch manifest、监控与告警约定 | `run_id`, `batch_id`, status, row_count, error summary, hash, start/end, last success | 文件批次记录 hash 与行数 | 只记录成功；无 run/batch；把 `updated_at` 当 freshness | 后端工程师 | planned |
| G3 | Data Contract | 固定来源输入、规范字段、存储与 API 契约 | 文件、payload、event、table、API | schema/contract、response model、version notes | 必填/nullable、type、unit、time、error/compatibility、contract tests | Pydantic response schema | schemaless 晋升；无文档 breaking change | 后端工程师 | planned |
| G4 | Field Standardization | 统一字段名称、类型、单位、空值、枚举、时间和金额语义 | 所有清洗/派生字段 | canonical field dictionary、source mapping | canonical name、type、null、unit、timezone、precision、mapping version | `itemId` 映射 `item_id`（candidate） | float 金额；编造 fallback；静默改变业务含义 | 数据 owner | planned |
| G5 | Schema Registry / Change Management | 管理来源/schema/字段/规则变化与兼容性 | source contract、table、event、API、mapping | schema registry entry、change record、migration/rollback PRP | version、compatibility、effective date、approval、deprecation | 来源新增字段先登记再晋升 | 自动接受破坏性变化；原地改历史 | 架构师/技术 owner | planned |
| G6 | Data Quality / Freshness | 校验完整性、唯一性、合理性、延迟和发布资格 | RAW 后到 API 前所有层 | DQ rules、thresholds、run summary、freshness SLO | `pass/warn/reject/quarantine`、不静默丢弃、lag/volume anomaly | SKU 缺失按已批准规则 warn | 用默认值掩盖失败；仅凭更新时间证明新鲜 | 数据 owner | planned |
| G7 | Lineage / Provenance | 追踪来源记录、转换规则和目标字段/数据集 | 表、字段、mart、API、AI 输出 | lineage matrix、run manifest、field mapping | `source_system`, endpoint/file/table, `raw_record_id`, `transform_rule_version`, `target_table/field`, run/batch | API 字段追溯到 canonical 和 RAW | 只写“来自数据库”；无规则版本即派生 | 架构师 | planned |
| G8 | Identity / MDM Governance | 管理多平台、多店铺、多 SKU、多 listing 的身份关系 | product、listing、store、account、user 等实体 | identity contract、mapping、merge/split history、review queue | 稳定内部 ID、context、confidence、evidence、人工确认优先 | `platform + store_id + item_id/listing_id` 候选 grain | SKU/MSKU 全局唯一；低置信度直发；静默 merge | 数据 owner | planned |
| G9 | Permission / Data Scope | 服务端限制能做什么、看哪些数据和字段 | 业务 API、导出、人工动作、AI retrieval | permission/resource key、scope contract、field classification | fail closed、selected entity validation、action/field permission | 产品页面 view permission + store scope | 仅前端隐藏；硬编码角色；NONE 仍返回数据 | 后端工程师 | planned |
| G10 | Data Classification / Sensitive Field | 分类并最小化敏感、机密与 secret 数据 | 采购价、利润、结算、广告费、员工信息、API secret 等 | field classification、access/retention/redaction plan | least privilege、mask、日志剔除、导出限制、删除处理 | 采购价字段级权限；Token 只由后端密钥管理 | 密钥进前端/文档/RAW；无关真实样本；默认全量导出 | 项目负责人/安全 owner | planned |
| G11 | Metric / Semantic Layer | 固定指标定义、grain、公式、时间与币种语义 | KPI、报表、MART、财务与运营指标 | metric dictionary、formula、owner/version | inclusion/exclusion、grain、source authority、time/currency semantics | “利润”需版本化 metric contract | 同名异义；从 MART 反推权威；隐藏公式 | 业务 owner | planned |
| G12 | Business Rules / Config | 把可变业务规则和小型参考配置版本化 | 费用规则、状态枚举、阈值、映射规则 | rule/config record、effective dates、approval/audit | `rule_version`, `effective_from/to`, reason, approver | 版本化费用规则 | 写死规则；覆盖历史；配置无 owner | 业务 owner | planned |
| G13 | Manual Override Governance | 让人工值与外部值分离、可审计、可撤销 | 人工维护、纠错、归档、映射确认、AI 建议采纳 | override record、approval、audit | before/after、operator、reason、source page/action、生效期 | 人工店铺别名另存 override | 改 RAW；sync 覆盖人工值；silent fallback | 业务 owner | planned |
| G14 | Audit / Operation Log | 记录谁在何时以何权限做了什么 | 写 API、高风险动作、审批、配置、任务操作 | immutable audit/operation event | actor、action、target、request/run ID、before/after、result | 批量归档操作日志 | 可编辑/删除 audit；日志含 secret；把 audit 当业务状态 | 技术 owner | planned |
| G15 | Retention / Archive Policy | 管理 RAW、业务、审计、文档、向量、快照与归档生命周期 | 所有持久化产物 | retention schedule、archive/delete/recovery plan | TTL、legal hold、删除传播、恢复审批 | 文档撤回同步清理索引 | 默认永久保留；Archive 服务热 API；静默恢复 | 数据 owner | planned |
| G16 | AI Governance | 控制模型输入、prompt、运行、成本、输出 Review 与采纳 | AI task/run/output | task approval、prompt/model version、run/review log | permission/data scope、input provenance、budget、human confirmation | AI 建议保持 candidate，人工采纳另记 | AI 自动写业务数据；读取 secret；绕过 scope | 项目负责人 | planned |
| G17 | Knowledge Governance | 治理 SOP/文档版本、发布状态、权限与检索索引 | doc、chunk、search/vector | doc/version registry、ACL、chunk lineage、publish/revoke record | owner、status、published_at、source/hash、可重建与删除传播 | 已发布 SOP 的带引用检索 | Draft 当正式依据；vector 当权威源；orphan chunk | 文档 owner | planned |
| G18 | Financial Reconciliation / Control Totals | 证明利润、广告、退款、结算、汇率、WFS 与仓储费用完整一致 | 财务来源、FACT、MART、导入、重算 | metric contract、reconciliation run、control totals、variance/approval | Decimal、currency/FX version、period、threshold、锁定与审计 | settlement 来源总额与 FACT 对账 | float；keyword 广告表全局汇总；无对账发布利润 | 项目负责人/财务 owner | planned |

## 关键边界

1. G0 必须先决定 source 是否接入、RAW 策略和权威等级；`candidate` 或 `legacy_reference` 不等于批准。
2. G2 的最低运行证据为 `run_id`、`batch_id`、status、row count、error 和 hash；对不适用字段必须解释。
3. G7 必须能从 target field 追到 source system、endpoint/file/table、raw record 和 transform rule version。
4. G8 处理身份，不承担产品详情、库存事实或页面 MART。
5. G10 覆盖采购价、利润、结算、广告费、员工信息与 API secrets；secret 不得进入业务数据层。
6. G13 必须防止人工值与外部同步值互相静默覆盖。
7. G18 适用于利润、广告、退款、结算、汇率、WFS 费用和仓储费，必须负责人确认。
8. Business Event、Audit Log、Lineage Record 是不同证据；CDC 仅为未来 `candidate` 能力，本轮不批准实现。

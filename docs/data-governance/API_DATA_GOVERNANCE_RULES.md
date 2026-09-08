# API / Table / Sync / Import 数据治理规则

> Status: 规则在负责人合并后为 `approved`；本文不批准任何具体实现。
> Scope: 新 API、新表、新同步任务、新导入和 AI 功能的强制前置检查。
> Non-goals: 不定义业务 endpoint、schema、表、migration、connector 或部署。

本文与 `docs/delivery/backend-data-source-decision-gate.md` 同时适用。业务数据 Source Decision 必须先达到限定范围的 `READY_FOR_PRP`，然后才能编写 API PRP；PRP 获批后才可实现。

## 通用前置清单

| 检查项 | 必须回答 | Blocking condition |
| --- | --- | --- |
| source decision | 来源、写入方、权威等级、短期/长期策略、退出条件 | 缺失、`NEED_OWNER_DECISION` 或超出 READY_FOR_PRP 范围 |
| raw policy | 是否 RAW_REQUIRED、按接口/文件的 raw_status、重放方式 | 应存 RAW 但缺失/未确认 |
| target data layer | Source/Landing/RAW/Standardized/Core/DIM/FACT/MART/MANUAL 等 | 未说明目标层或让 RAW/MART 充当权威 |
| field contract | 字段名、类型、null、单位、时间、金额、枚举、版本 | 编造字段/fallback 或契约不完整 |
| data scope | resource/page key、范围来源、selected entity 校验 | unknown/missing/NONE 未 fail closed |
| permission | page/action/data/field/high-risk permission | 仅前端隐藏或硬编码角色 |
| sensitive field level | PII、财务、员工、secret 等分类与脱敏 | 未分类敏感字段或前端接收 secret |
| lineage | source/endpoint/file/table、raw、rule version、target、run/batch | 无法字段级/运行级追溯 |
| DQ | pass/warn/reject/quarantine、阈值、错误保留 | 无 DQ 即发布或静默丢弃 |
| audit | actor、action、request/run ID、before/after（如写入） | 人工/高风险动作无审计 |
| manual override impact | 来源值与人工值是否分开、优先级与冲突处理 | sync 覆盖人工值或人工改 RAW |
| financial impact | 金额、币种、规则版本、control totals、审批 | 涉及金额但未应用财务规则 |
| AI impact | input/retrieval、ACL、prompt/model/version、Review、cost | AI 读越权数据或自动写业务数据 |
| retention impact | RAW、业务、audit、archive、cache/vector 的期限与删除传播 | 默认永久留存或无法删除派生副本 |
| identity mapping impact | identity grain、mapping/confidence、冲突队列 | SKU/MSKU 全局唯一或低置信度直发 |

新表必须额外说明归属层、owner、grain、主键/identity、writer/readers、authority、retention、lineage、DQ、敏感性与删除/回滚。不能因本清单存在就跳过表或 migration PRP。

## A. 查询类 API

| Required decision | 要求 |
| --- | --- |
| 读取层 | 明确 DIM、FACT、MART、MANUAL 或 `legacy readonly`；RAW 默认禁止 |
| 旧系统读取 | 必须有 `READ_LEGACY_TEMPORARILY` 决策、只读账号、表/字段 allowlist 和退出条件 |
| contract | Pydantic response model、字段语义/null/单位/时间/金额、pagination/filter contract |
| security | permission key、resource key、data scope、字段级脱敏；fail closed |
| platform | `request_id`、统一 error model、`{ success, data, error, meta, request_id }` envelope |
| quality | 新鲜度、DQ warning、来源限制和 partial data 行为 |

示例（candidate）：产品查询若获批只读旧库，只能读取 Source Decision 允许字段；不得顺手加入价格、库存或负责人字段。

## B. 写入类 API

| Required decision | 要求 |
| --- | --- |
| 写入目标层 | 明确 Core/DIM/FACT/MANUAL 等；禁止写 RAW 或直接写 MART 权威值 |
| manual override | 说明是否属于人工覆盖、与外部字段隔离方式、effective value 解析 |
| sync impact | 外部同步是否可能冲突；禁止任一方向静默覆盖 |
| audit | before/after、operator、reason、source page/action、request ID |
| approval | 金额、删除、批量、高风险字段需二次确认/审批/可回滚 |
| idempotency | request/idempotency key、重复提交与部分失败行为 |

## C. 导入类功能

| Required decision | 要求 |
| --- | --- |
| source file | 来源注册、owner、格式、版本、敏感等级 |
| RAW | 原文件和 raw row 可追溯存储；保留 header、`row_number`, `file_hash`, uploader/time |
| batch | 唯一 `batch_id`、重复文件识别、状态和 control totals |
| mapping | header mapping 与版本；未知列和缺列处理 |
| DQ | 行级/批次级 pass/warn/reject/quarantine；错误不得静默丢失 |
| publish | 发布目标层、原子性/部分成功规则、重放和回滚 |

## D. 同步类任务

| Required decision | 要求 |
| --- | --- |
| source registry | 精确到平台、接口/文件类型、版本、owner 与 authority |
| raw policy | raw_status、payload/error/empty page 保存与凭据剔除 |
| ingestion run/batch | `run_id`, `batch_id`, status, row_count, error summary, hash |
| retry policy | 可重试错误、次数/backoff、停止条件；禁止无限重试 |
| idempotency | key、分页重复、任务重跑、upsert/version 策略 |
| watermark | 来源 cursor/时间语义、推进条件、回退与重放 |
| observability | start/end、last success、lag、volume anomaly、告警 owner |
| lineage | source → raw → rules → target 的 run/field 证据 |

同步按钮只能创建后端任务或查询任务状态；前端与业务 route handler 不得直接实时批量拉外部平台。

## E. AI 类功能

| Required decision | 要求 |
| --- | --- |
| input source | 允许的结构化字段/文档/用户输入及敏感性 |
| retrieval source | doc/version/chunk 或 table/record 引用、authority、可重建性 |
| permission/data scope | 检索前服务端校验；不得依赖模型过滤越权结果 |
| prompt/model | prompt template version、model allowlist、用途与预算 |
| cost | token/用量、金额、operator、模块与 request/run ID |
| output review | candidate 状态、citation、质量检查、reviewer/feedback |
| manual confirmation | 采纳必须生成独立 override/event/audit；禁止自动写权威层 |

## Forbidden patterns

- 直接从外部 API 返回业务接口结果，不落受治理证据和层级。
- 直接从 RAW 给前端或普通业务 API 展示。
- 没有 Source Decision 就接入来源、建表、写 sync/import 或业务 API。
- 没有 DQ 就发布；不合格数据静默丢弃。
- 没有 audit 就写人工字段、执行批量/删除/高风险动作。
- 没有 lineage 就清洗、派生或发布。
- 没有 financial policy、metric definition、control totals 就计算利润或发布财务指标。
- 没有 permission/data scope 就暴露业务或敏感字段。
- API route 实时批量拉外部平台；frontend 直连数据库、RAW 或外部平台。
- 用 MART、cache、vector index 或 AI output 反推并覆盖权威数据。

## PRP 与 Release Gate

1. PRP 必须逐项引用本清单的决策或写明不适用理由，不能机械复制。
2. `candidate`、`legacy_reference`、离线 integrations 文档或 Draft PRP 都不构成实现授权。
3. 实现必须保持一个任务一个模块/页面/API、一个分支、一个 PR，可独立测试与回滚。
4. 完成 Review 必须核对 schema/contract、permission/data scope、DQ、lineage、audit、敏感信息、文档和 tests；负责人本人执行最终 Git 上传与合并动作。

# 数据治理目录（Data Governance Catalog）

> 规则状态：仅在负责人 Review 并合并后成为 `approved` 基线。
> 实现状态：`planned`；本目录不证明任何表、任务、API、控制或平台能力已经存在。
> Scope: 数据治理文档入口、术语、阅读顺序与通用门禁。
> Non-goals: 不创建 schema、migration、同步、API 或迁移旧数据。

## 目录目的

本目录是 SZZSBJ 数据治理边界入口，规定未来 API、数据表、同步任务、导入、报表、AI 知识和人工更正在实现前如何确定来源、层级、字段、身份、权限、质量、血缘和审计。

这里保存治理规则，不是数据库 migration、schema 设计、旧数据迁移计划、实现 PRP 或生产系统访问授权。项目仍是 greenfield；`old-system/` 及其报告仅是只读 `legacy_reference` 证据。

## 前置规则

先遵守 `AGENTS.md`、`docs/DATA_SOURCE_AND_LINEAGE_RULES.md`、`docs/data-sources/database-layering-standard.md`、`docs/data-sources/field-standardization-standard.md` 和 `docs/delivery/backend-data-source-decision-gate.md`。

## 推荐阅读顺序

1. `data-layer-catalog.md`
2. `governance-plane-catalog.md`
3. `source-registry-and-raw-policy.md`
4. `field-cleaning-pipeline.md`
5. `identity-mdm-policy.md`
6. `manual-override-policy.md`
7. `financial-reconciliation-policy.md`
8. `ai-knowledge-governance-policy.md`
9. `API_DATA_GOVERNANCE_RULES.md`

## 文件用途

| 文件 | 用途 | 规则状态 | 实现状态 |
| --- | --- | --- | --- |
| `data-layer-catalog.md` | 逻辑数据层和允许流向 | 合并后 approved | planned |
| `governance-plane-catalog.md` | G0-G18 横向治理控制 | 合并后 approved | planned |
| `field-cleaning-pipeline.md` | 0-18 字段清洗与发布流程 | 合并后 approved | planned |
| `source-registry-and-raw-policy.md` | 来源登记、决策与 RAW 保存 | 合并后 approved | planned |
| `identity-mdm-policy.md` | 业务身份、映射、别名与合并 | 合并后 approved | planned |
| `manual-override-policy.md` | 人工更正、覆盖与审计 | 合并后 approved | planned |
| `financial-reconciliation-policy.md` | 财务权威、control totals 与对账 | 合并后 approved | planned |
| `ai-knowledge-governance-policy.md` | AI、文档、向量、检索与 provenance | 合并后 approved | planned |
| `API_DATA_GOVERNANCE_RULES.md` | API/表/同步/导入强制检查清单 | 合并后 approved | planned |

## 状态词汇

| 状态 | 含义 |
| --- | --- |
| `planned` | 已规划能力或产物，但没有实现证据。 |
| `approved` | 负责人批准精确范围；不等于已实现。 |
| `implemented` | 仓库证据与测试证明能力存在。 |
| `candidate` | 等待验证和批准的来源、映射、层级或控制。 |
| `legacy_reference` | 只读历史证据，不能单独成为新系统权威。 |

禁止把 `candidate` 或 `legacy_reference` 写成 `approved` 或 `implemented`。合并本目录只代表规则获批，不代表目录中描述的能力已经建设。

## 强制门禁

任何新 API、新表、新同步/导入任务、MART/read model、人工写入、数据导出、财务计算和 AI 知识摄取必须：

1. 确定来源与权威等级；
2. 选择最少且必要的数据层和治理平面；
3. 记录字段、身份、新鲜度、留存、权限、血缘和失败处理；
4. 涉及业务数据时，先完成 Source Decision，再写 API PRP；
5. 实现或访问生产系统前，另有 PRP 并取得负责人批准。

只有 PRP 证明数据仍可识别、可审计、可恢复且安全时，才可省略物理层。本目录任何条目都不授权数据库访问、外部 API、部署、迁移或代码修改。

## 本轮状态与非目标

- 本轮只落文档，不代表已经建表、迁移旧数据或实现产品 API。
- 不批准生产 schema、实际表名、migration 顺序、具体留存时长或供应商。
- 不复制旧系统架构；离线接口文档不自动批准外部接口。
- 前端不得直接读取数据库、RAW、密钥或外部平台。
- 不得以“以后再做”为由静默省略数据质量、权限、血缘或审计。

## 示例与禁止模式

| 场景 | 正确入口 | status |
| --- | --- | --- |
| 新产品查询 API | 先完成接口级 Source Decision，再写独立 API PRP | candidate |
| 旧系统表或报告 | 作为只读调查证据，标记 `legacy_reference` | legacy_reference |
| 新同步任务 | 先登记来源、RAW 策略、目标层、DQ、lineage 和回滚边界 | planned |

Forbidden patterns：把本目录当 migration 施工图；把 `planned` 当 `implemented`；因为文档列出某层就预先建空表；绕过 Source Decision/PRP；复制旧系统混合架构；在治理文档中写入真实密钥或生产样本。

# 数据来源与字段血缘规则

## 文件用途

本文件用于约束 AI 在开发页面、报表、同步任务时，必须说明字段从哪里来、经过哪些转换、最终如何展示。

## 必须说明的数据来源

常见来源包括：Walmart、Amazon、TEMU、领星、广告 API、订单 API、库存 API、退款 API、结算文件、old-system、人工导入 Excel、新系统数据库。

## 字段血缘必须包含

| 项目 | 说明 |
|---|---|
| 源系统 | 数据来自哪个平台或表 |
| 原始字段 | 源字段名称 |
| 标准字段 | 新系统字段名称 |
| 转换规则 | 是否清洗、格式化、换算 |
| 计算规则 | 是否参与公式 |
| 展示位置 | 哪个页面展示 |
| 更新频率 | 实时、定时、手工导入 |
| 风险 | 空值、重复、延迟、口径不清 |

## 页面开发要求

AI 开发页面前，必须输出页面字段数据来源说明。涉及利润、回款、广告花费、退款率、库存预警等字段时，必须明确公式和数据来源。

## 后端接口数据源决策

后端业务接口进入 PRP 前，必须按 `docs/delivery/backend-data-source-decision-gate.md` 对每个数据集或字段组选择下列分类之一：

当前负责人决定下，旧系统只可作为 `legacy_reference`、source investigation evidence、field meaning reference、reconciliation input 或 migration acceptance evidence。新系统业务 API 不得运行时读取旧库或将其作为 fallback；新实现必须从 Data Layer Foundation / Source Registry / RAW / ingestion / read model 路线开始。超出证据用途的历史例外必须由负责人另行明确批准；当前没有获批例外。

| 分类 | 定义与边界 |
|---|---|
| `READ_LEGACY_TEMPORARILY` | 历史已取代分类，仅为兼容既有决策记录而保留；当前不得用于授权新系统业务 API 运行时读取旧 MySQL。 |
| `REBUILD_SYNC` | 外部平台是权威来源，新系统重新建设 integration、Celery 同步、标准化存储和质量检查。不得在 API route 中实时批量拉取外部平台数据。 |
| `MIGRATE_ONCE` | 有限的人工维护或历史主数据一次性迁入新 PostgreSQL；必须包含数量核对、字段映射、切换点和回滚方案，核对后切换所有权。 |
| `NEW_SYSTEM_OWNED` | 新系统产生并维护的数据或配置，不依赖旧库作为持续权威来源。 |
| `ARCHIVE_ONLY` | RAW、backup、临时、废弃或仅供审计观察的数据，不进入第一期业务接口。 |
| `NEED_OWNER_DECISION` | 临时阻塞状态，不是最终数据策略；在负责人决定前禁止实现。 |

聚合接口不得使用含糊的 `MIXED` 分类，必须按数据集或字段组分别分类。禁止默认双写，也不得把多个系统同时视为未定义优先级的权威来源。

任何仍依赖 `READ_LEGACY_TEMPORARILY` 的历史结论均不得直接进入实现，必须按当前 `new-system-data-layer-first` 决定重新完成来源、ingestion、标准层/Core 和 read model（如确有必要）的决策。

接口总体状态只能是：

```text
READY_FOR_PRP
BLOCKED_BY_OWNER_DECISION
```

只有所有数据集均已形成可执行策略且不存在未解决的 `NEED_OWNER_DECISION` 时，才可标记 `READY_FOR_PRP`；否则必须标记 `BLOCKED_BY_OWNER_DECISION`。

## 模板

| 页面字段 | 数据来源 | 源字段 | 转换/计算 | 展示口径 | 风险 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

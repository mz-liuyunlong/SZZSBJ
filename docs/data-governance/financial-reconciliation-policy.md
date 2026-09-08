# 财务与对账治理策略

> Status: 规则在负责人合并后为 `approved`；指标、表、任务和对账实现均为 `planned`。
> Scope: 利润、广告费、退款、结算、WFS、仓储、采购价、头程运费和汇率。
> Non-goals: 不定义具体公式、会计政策、阈值、数据源或历史重算方案。

财务、利润、成本、库存估值、广告、结算、退款均是高风险口径。任何 Source Decision、PRP、实现与修正都必须由负责人确认，不能与普通产品字段混入同一 PRP。

## 金额与汇率契约

| 类别 | 必需元数据 | 硬规则 |
| --- | --- | --- |
| 金额 | `amount`, `currency_code`, `precision`, `scale`, `rounding_rule` | 所有财务金额使用 `currency_code` 和 Decimal/`numeric(18,4)` 等获批精度；禁止 float、默认币种和 canonical 裸 `currency` |
| 汇率 | `fx_rate`, `fx_date`, `fx_source`，可附加 `fx_rate_version`，并保留原币金额 | 必须记录实际汇率值；`fx_date` 是适用日期，`fx_source` 是汇率来源；按业务日期选择获批版本，不得用当前汇率覆盖历史 |
| 期间 | `business_date`, `source_period`, `settlement_period` | 明确 America/Los_Angeles 业务日、来源期间、结算期间；不得混用 |
| 规则 | `metric_definition`, `rule_version`, `effective_from/to` | 公式、符号、包含/排除、粒度和锁定策略均须版本化 |

`currency`、`fx_rate_source`、`fx_rate_date` 只能作为来源字段、外部字段或旧系统字段别名，并通过 lineage 分别映射到 canonical `currency_code`、`fx_source`、`fx_date`。`fx_rate_version` 仅是汇率表、供应商或规则版本元数据，不能替代实际汇率值 `fx_rate`。Reconciliation 和 control totals 必须基于上述 canonical 金额字段，不得基于来源别名字段建立口径。

广告费、退款、结算、WFS 费用、仓储费、采购价、头程运费必须分别记录来源、字段口径、粒度、时间、币种、完整性和权威等级；名称相似不代表可相加或 fallback。

## Reconciliation 记录

| 字段/实体 | 说明 |
| --- | --- |
| `reconciliation_run` | 一次可重放、可审计对账运行，关联 run/batch、规则版本与输入版本 |
| `control_total` | 来源或目标在已声明粒度、币种、期间下的控制总额/计数 |
| `variance_amount` | 同币种同口径下的精确差异金额 |
| `variance_rate` | 分母和零值处理明确的差异率 |
| `threshold` | 版本化阈值及单位，不得写死在页面 |
| `accepted_by` | 有权限接受差异的 principal |
| `accepted_reason` | 具体理由与证据引用 |
| `source_period` | 来源覆盖期间 |
| `settlement_period` | 结算/锁定期间 |
| `business_date` | 业务归属日期，不等于 ingested/processed 时间 |

## Control totals 与对账

1. 财务数据必须在来源批次、标准化、FACT 与 MART/响应之间定义适用的 control totals，例如记录数、订单/结算数量、原币金额与目标币金额。
2. 不同 grain、币种、期间或状态的 totals 不得直接比较；必须先按 metric contract 对齐。
3. 差异必须为 pass/warn/reject/quarantine/owner review 之一，并记录阈值、规则版本、原因与处理人。
4. MART 是派生读模型，不能反推成为权威财务事实；重建必须回到获批 FACT/Core 和规则版本。
5. 不得直接用 keyword 维度广告花费表做全局金额汇总，除非 Source Decision 和 metric contract 证明其金额口径完整、无重叠且覆盖目标范围。
6. 财务修正必须走 manual override + audit；不得改 RAW、删除差异或覆盖已锁定历史。

## Metric definition 最低要求

| 项目 | 要求 |
| --- | --- |
| 名称与业务含义 | 中文/英文稳定名称，说明用于什么决策 |
| grain | SKU/listing/order/day/store/account/settlement 等精确粒度 |
| formula | 输入字段、符号、税费、退款、取消、分摊、FX 与舍入顺序 |
| inclusion/exclusion | 状态、日期、平台、店铺、异常记录与延迟处理 |
| source authority | 每个组成字段的获批权威来源与 lineage |
| time semantics | business date、source period、settlement period、timezone |
| currency semantics | 原币、目标币、FX 版本、精度与舍入 |
| owner/version | owner、reviewer、rule version、生效期、变更原因 |

## 权限与敏感性

- 成本、采购价、头程运费、WFS/仓储费用、利润、广告支出、退款、结算和 FX 明细属于敏感字段。
- 后端必须执行 page/action/data/field permission 与 data scope；前端隐藏列不是安全控制。
- 导出、批量重算、接受差异、解锁期间和人工覆盖属于高风险动作，需二次确认、审批、审计和可回滚。
- 日志、错误、测试与 AI 输入不得暴露未经授权的真实金额明细。

## 示例（非口径批准）

| 情况 | 处理 | status |
| --- | --- | --- |
| 来源结算总额与 FACT 不一致 | 保留双方 control total，按阈值 quarantine/owner review | candidate |
| 新汇率版本发布 | 只影响生效期内未锁定计算；历史默认不重写 | candidate |
| MART 金额与 FACT 不一致 | 重建/调查 MART，不以 MART 回写 FACT | candidate |

## Forbidden patterns

- 利润派生链与普通产品查询共用一个无专项批准的 PRP。
- 金额用 float、无币种、无舍入规则或无原币值。
- 把广告、退款、结算、WFS、仓储、采购与头程费用视为同一口径。
- 用最新 FX 重算并覆盖已结算历史。
- 无 control totals、lineage 或 metric definition 即发布财务指标。
- 人工 SQL/表格改金额且没有 before/after、审批与审计。

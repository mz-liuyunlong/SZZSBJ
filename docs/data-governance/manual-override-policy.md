# 人工维护与覆盖治理策略

> Status: 规则在负责人合并后为 `approved`；人工写入模型与页面能力均为 `planned`。
> Scope: 人工维护、纠错、覆盖、归档及 AI 建议采纳。
> Non-goals: 不批准任何具体写接口、字段、表、权限或审批流。

## 核心规则

1. 人工字段不得直接覆盖外部同步字段；来源值与人工值必须分开存储。
2. 外部同步不得静默覆盖已人工确认字段，也不得把人工值回写 RAW。
3. 页面可按获批解析规则合并展示外部值与人工值，但必须能说明当前 effective value 来自哪里。
4. 人工覆盖必须是字段级、实体级、范围级和时间级的显式记录；不得默认全局永久生效。
5. 人工生命周期、负责人、采购价、WFS 配送费、备注、归档状态必须可审计；其中金额、成本、利润、结算类变更属于高风险。
6. 人工归档/解档必须保留原因和 before/after，不能物理删除业务证据。
7. AI 建议与人工采纳是两条记录：AI 输出不能直接写 manual override，必须由有权限人员确认。

## Override 必需字段

| 字段 | 要求 |
| --- | --- |
| target entity/field | 明确实体、字段、数据 scope 与原来源 |
| `before_value` | 修改前 effective value；敏感值按字段权限保护 |
| `after_value` | 人工值；须通过字段 contract 与 DQ |
| `updated_by` | 可审计 principal，不允许匿名/共享账号 |
| `updated_at` | UTC 存储；展示时按项目时区规则 |
| `reason` | 业务原因，不能只写“修正”或空文本 |
| `source_page` | 发起页面或受控入口 |
| `source_action` | create/update/archive/unarchive/approve/reject/adopt_ai 等 |
| `approval_status` | 高风险必填；pending/approved/rejected/revoked 等 |
| effective range | 需要时记录 `effective_from/effective_to` |
| audit reference | request_id、audit event、批准人/时间、相关证据 |

## 解析优先级

| 状态 | 展示/使用规则 | 同步行为 |
| --- | --- | --- |
| 无有效人工覆盖 | 使用已批准的 external/canonical 值 | 正常更新来源字段 |
| 有有效且已批准覆盖 | 使用人工值，并显示来源/状态（权限允许时） | 只更新来源字段，不覆盖人工记录 |
| 覆盖过期/撤销 | 回到当时有效的来源/canonical 值 | 保留完整历史 |
| 来源与人工值冲突 | 记录 issue；按已批准优先级展示 | 禁止静默消除冲突 |
| AI 建议未采纳 | 不影响业务 effective value | 只留 AI run/output 证据 |

## 高风险控制

- 采购价、成本、WFS 配送费、利润、结算、退款、汇率等金额字段需要字段级权限、二次确认、审批（如规则要求）、审计和可回滚。
- 负责人/lifecycle/归档等影响业务范围或责任的数据需 action permission 与 data scope 校验。
- 批量覆盖必须显示影响数量、范围与字段，使用幂等 request，并产生 control total；不得在 UI 静默执行。
- 已结算或锁定期间的数据默认不得因新人工值重算；例外必须单独 PRP 和负责人批准。

## 示例（仅规则示例）

| 场景 | 正确处理 | status |
| --- | --- | --- |
| 人工更正备注 | 新增 manual record，保留 before/after、operator、reason | candidate |
| 同步返回不同采购价 | 更新 external value；保留已批准 manual override 并产生冲突 issue | candidate |
| 采用 AI 建议标签 | 先存 AI output，再由人工 `adopt_ai` 动作创建 override/event/audit | candidate |

## Forbidden patterns

- `update external synced column directly`
- `overwrite manual value from sync job`
- missing operator
- missing reason
- no before/after
- no audit trail
- silent fallback
- 将人工值和来源值写进同一列后无法区分。
- 用前端本地存储替代后端审计记录。
- 物理删除 override 或 audit 以“恢复原值”。

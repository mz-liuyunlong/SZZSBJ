# Manual Override Boundary Rules

## Required Rules

- 人工值不得直接覆盖 source value；分别保存 `source_value`、`manual_value` 和按批准规则解析的 `effective_value`。
- 每次覆盖保留 target、field、before/after、operator、reason、time、effective range、approval 和 request/audit reference。
- 同步只更新来源值，不覆盖人工记录；人工值不回写 RAW。
- UI 在权限允许时说明 effective value 来源和冲突状态。
- 撤销通过新状态/补偿记录完成，不删除历史。
- AI 建议必须由有权限人员确认后，才可创建独立 override/audit。

金额、权限、归属、生命周期和批量操作属于高风险，必须另有 action/field permission、确认、审批和回滚。

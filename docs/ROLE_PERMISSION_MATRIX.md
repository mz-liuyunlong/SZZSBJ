# 角色权限矩阵

## 文件用途

本文件用于逐步记录系统角色和权限边界。具体角色可根据实际团队调整。

## 初始角色建议

| 角色 | 说明 |
|---|---|
| owner | 系统负责人 / 老板 |
| admin | 管理员 |
| operation_manager | 运营主管 |
| operator | 运营 |
| finance | 财务 |
| purchase | 采购 |
| customer_service | 客服 |
| readonly | 只读人员 |

## 权限矩阵模板

| 模块 | 操作 | owner | admin | operation_manager | operator | finance | purchase | readonly |
|---|---|---|---|---|---|---|---|---|
| 财务 | 查看利润 | 是 | 是 | 是 | 待确认 | 是 | 否 | 否 |
| 财务 | 导出财务 | 是 | 是 | 待确认 | 否 | 是 | 否 | 否 |
| 广告 | 修改建议 | 是 | 是 | 是 | 待确认 | 否 | 否 | 否 |
| 系统 | 修改权限 | 是 | 是 | 否 | 否 | 否 | 否 | 否 |

AI 新增敏感操作时必须更新或引用本文件。

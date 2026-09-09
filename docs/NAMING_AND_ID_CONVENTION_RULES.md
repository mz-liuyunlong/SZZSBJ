# Naming and ID Convention Rules

## Required Rules

- 名称必须表达业务语义和 grain；禁止 `data1`、`temp2`、`misc` 等含糊命名。
- Python/数据库字段使用 `snake_case`，React 组件/类型使用 `PascalCase`，JS/TS 变量使用 `camelCase`，文档文件沿用目录既有规则。
- API path 使用小写 kebab-case 或既有 REST 约定；permission key 使用稳定的 `module.resource.action`。
- 新实体使用新系统稳定内部 ID；SKU、MSKU、ItemID、店铺外部 ID 均不得默认作为跨平台全局 ID。
- 外部 ID 必须携带 provider/platform/store/account 上下文和 lineage。
- `request_id`、`run_id`、`batch_id`、entity ID 各自独立，不得互换。
- 枚举/status 只有一个 canonical 定义；禁止前后端各造一套。
- 重命名字段、ID 或 permission key 需说明兼容、迁移和弃用方案并经负责人批准。

## Stop Conditions

实体 grain、唯一性、来源或兼容影响不明确时，不得创建字段或约束；先完成 Source Decision/PRP。

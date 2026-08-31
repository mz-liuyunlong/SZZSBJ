# 权限与操作日志规则

## 文件用途

本文件用于约束 AI 如何设计敏感接口、写操作和操作日志。

## 敏感操作

以下操作必须有权限判断，并记录操作日志：删除数据、导出财务数据、修改成本、修改库存、修改广告出价或预算、修改 Listing 内容、触发平台同步、执行大文件导入、执行 AI 自动优化建议、修改用户权限、修改系统配置。

## 操作日志建议字段

```text
id
operator_id
action
target_type
target_id
before_snapshot
after_snapshot
ip
user_agent
created_at
```

AI 不允许新增无权限保护的敏感接口，也不允许新增无法追踪操作者的写操作。高风险操作必须有二次确认。

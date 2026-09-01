# 权限与操作日志规则

## 1. 权限最终原则

系统不写死业务角色。角色由超级管理员在页面上动态创建和配置。

代码只允许判断 `permissionKey`，禁止判断角色名。

错误：

```python
if user.role == "finance":
    ...
```

正确：

```python
require_permission("finance.profit_center.view")
```

## 2. 权限层级

```text
页面权限
动作权限
数据权限
字段权限
API 权限
高危动作权限
```

## 3. 敏感操作

以下必须有权限判断、二次确认或审批，并记录审计日志：

```text
删除数据
导出财务数据
修改成本
修改库存
修改广告出价或预算
修改 Listing 内容
触发平台同步
执行大文件导入
执行 AI 自动优化建议
修改用户权限
修改系统配置
修改集成 Token
修改飞书 Webhook
修改费用规则
历史重算
```

## 4. 审计日志字段

```text
id
operator_id
action
target_type
target_id
before_snapshot
after_snapshot
request_id
ip
user_agent
created_at
```

## 5. 数据权限

每个页面必须支持独立数据权限配置：

```text
all
own
direct_reports
team
org_tree
selected
custom
none
```

前端隐藏不是安全措施，后端必须强制过滤。

详细规则见：

```text
docs/business-rules/permission-model.md
docs/business-rules/organization-and-data-scope.md
```

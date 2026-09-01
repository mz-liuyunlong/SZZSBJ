# 权限模型规则

## 1. 总原则

```text
角色由超级管理员配置。
代码不写死角色名。
系统只维护 permissionKey。
页面、按钮、API、数据范围都绑定 permissionKey。
```

禁止：

```python
if user.role == "admin":
    ...
```

必须：

```python
require_permission("settings.role_management.view")
```

## 2. 权限层级

| 层级 | 说明 |
|---|---|
| 页面权限 | 能不能打开页面 |
| 动作权限 | 能不能导入、导出、编辑、审批、删除、重算 |
| 数据权限 | 进入页面后能看哪些店铺、负责人、SKU、账号 |
| 字段权限 | 能不能看利润、成本、供货价等敏感字段 |
| API 权限 | 每个接口 required permissionKey |
| 高危动作 | 二次确认 + 审批 + 审计 + 可回滚 |

## 3. permissionKey 命名

页面：

```text
<module>.<page>.view
```

动作：

```text
<module>.<page>.<action>
```

示例：

```text
sales.daily_sales.view
sales.daily_sales.export
products.product_management.edit
data_center.api_docs.view
data_center.data_import.rollback
finance.profit_center.recalculate
settings.role_management.assign_permission
settings.integration_config.edit
```

## 4. 角色和权限关系

- 一个用户可以绑定多个角色。
- 一个角色可以绑定多个权限点。
- 用户可以有单独覆盖权限。
- 普通页面权限默认取并集。
- 财务、高危、权限管理页面可配置为最小授权策略。

## 5. 前后端要求

前端：

```text
根据 permissionKey 控制菜单和按钮显示。
```

后端：

```text
必须再次校验 permissionKey。
前端隐藏不是安全措施。
```

## 6. 权限变更审计

以下必须写入 `audit_permission_change_log`：

```text
创建角色
停用角色
分配权限
移除权限
修改用户角色
修改数据权限
修改高危权限
修改字段权限
```

## 7. 保护规则

```text
不能删除最后一个超级管理员能力账号
不能停用最后一个拥有 settings.role_management 权限的账号
普通管理员不能授予自己没有的权限
高危权限变更必须二次确认
```

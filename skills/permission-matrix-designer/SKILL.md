# Skill: Permission Matrix Designer

## 用途

本 Skill 用于设计页面、接口、按钮、导出、敏感操作的角色权限矩阵。

## 必须读取

1. `docs/PERMISSION_AND_AUDIT_RULES.md`
2. `docs/ROLE_PERMISSION_MATRIX.md`

## 输出格式

```md
## 权限设计

### 功能 / 页面
### 角色矩阵
### 敏感操作
### 操作日志字段
### 二次确认需求
### 风险点
```

## 强制规则

1. 敏感操作必须有权限。
2. 写操作必须可追踪操作者。
3. 财务和广告高风险操作必须二次确认。

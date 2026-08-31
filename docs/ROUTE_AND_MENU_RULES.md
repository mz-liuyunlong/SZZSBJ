# 路由与菜单规则

## 文件用途

本文件用于约束前端页面路由、菜单和权限 key 的命名。

## 命名建议

路由 / 菜单 key 使用业务层级：

```text
ads.campaigns.list
ads.searchTerms.list
ads.negativeKeywords.list
products.list
sales.daily
finance.profitCenter
warehouse.inventoryWarning
ai.optimizationLogs
```

## 规则

1. 每个页面必须有唯一 route key。
2. 菜单配置集中管理。
3. 页面文件路径和路由路径应保持对应。
4. 一级菜单、二级菜单、页面权限要分开。
5. AI 不允许随便新增重复菜单。
6. 新增页面时必须说明路由、菜单位置、权限 key。

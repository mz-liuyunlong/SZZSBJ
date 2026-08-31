# Skill: Rebuild Mapping Planner

## 用途

本 Skill 用于把 old-system 的旧页面、旧 API、旧表、旧任务映射为新系统的页面、API、数据模型和任务。

## 必须读取

1. `docs/REBUILD_MAPPING_RULES.md`
2. `docs/OLD_SYSTEM_READONLY_RULES.md`

## 输出格式

```md
## 旧功能重建映射

### 读取旧文件
### 旧页面 / 旧 API / 旧表
### 新页面 / 新 API / 新模型
### 保留逻辑
### 废弃逻辑
### 字段映射
### 风险点
### 待确认问题
```

## 强制规则

1. 只映射业务规则，不复制旧代码。
2. 映射结果写入 `docs/old-system-analysis/`。
3. 涉及财务、库存、广告、退款必须标记待确认。

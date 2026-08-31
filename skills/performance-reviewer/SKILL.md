# Skill: Performance Reviewer

## 用途

本 Skill 用于审查大表查询、报表、导入导出、外部 API 批量请求的性能风险。

## 必须读取

1. `docs/PERFORMANCE_RULES.md`
2. `docs/DATABASE_RULES.md`
3. `docs/DATA_SYNC_RULES.md`

## 输出格式

```md
## 性能审查

### 影响数据量
### 查询过滤条件
### 分页策略
### 索引建议
### 是否需要 Celery
### 前端渲染风险
### 外部 API 限流风险
### 优化建议
```

## 强制规则

1. 禁止全表查询。
2. 大数据报表必须考虑后台任务。
3. 必须说明分页和索引。

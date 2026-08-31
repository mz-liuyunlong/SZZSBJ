# Skill: Data Sync Designer

## 用途

本 Skill 用于设计平台数据同步任务，包括批次、幂等、增量、重试和错误报告。

## 必须读取

1. `docs/DATA_SYNC_RULES.md`
2. `docs/DATA_QUALITY_RULES.md`
3. `docs/BACKGROUND_TASK_DEVELOPMENT_RULES.md`

## 输出格式

```md
## 数据同步设计

### 来源平台
### 同步对象
### 全量/增量策略
### 去重键
### 批次字段
### 异常处理
### Celery 任务
### 数据质量报告
### 重试策略
```

## 强制规则

1. 同步任务必须可追踪批次。
2. 必须防重复写入。
3. 必须考虑部分成功和错误明细。

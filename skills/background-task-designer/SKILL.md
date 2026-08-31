# Skill: Background Task Designer

## 用途

本 Skill 用于指导 AI 设计 Celery 后台任务。

## 必须读取

1. `docs/BACKGROUND_TASK_DEVELOPMENT_RULES.md`
2. `docs/CODE_COMMENT_RULES.md`
3. `docs/PERMISSION_AND_AUDIT_RULES.md`

## 输出格式

```md
## 后台任务设计方案

### 任务名称

### 任务用途

### 输入参数

### 输出结果

### 是否幂等

### 重试策略

### 会修改哪些表

### 是否调用外部 API

### 是否可能产生费用

### 前端如何查询任务状态

### 失败后用户看到什么

### 日志与安全要求
```

## 强制规则

1. 固定使用 Celery。
2. 不引入第二套任务系统。
3. Task 不堆复杂业务逻辑。
4. 任务必须可追踪状态。
5. 日志不得输出密钥。

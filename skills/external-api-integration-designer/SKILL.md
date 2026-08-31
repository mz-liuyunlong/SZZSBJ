# Skill: External API Integration Designer

## 用途

本 Skill 用于接入第三方 API 前设计认证、超时、重试、限流、错误转换和脱敏策略。

## 必须读取

1. `docs/EXTERNAL_API_INTEGRATION_RULES.md`
2. `docs/SECURITY_RULES.md`
3. `docs/BACKGROUND_TASK_DEVELOPMENT_RULES.md`

## 输出格式

```md
## 外部 API 接入方案

### API 来源
### 认证方式
### 请求封装目录
### 超时
### 重试
### 限流
### 错误转换
### 日志脱敏
### 是否走 Celery
### 测试方式
```

## 强制规则

1. 前端不直接调用敏感外部 API。
2. 不在 Route 中散落外部请求。
3. 批量调用必须考虑 Celery 和限流。

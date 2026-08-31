# Skill: LLM Provider Adapter Designer

## 用途

本 Skill 用于设计系统内 AI 模型调用层，避免业务代码散落直接调用 SDK。

## 必须读取

1. `docs/LLM_PROVIDER_ADAPTER_RULES.md`
2. `docs/AI_FEATURE_SAFETY_RULES.md`
3. `docs/SECURITY_RULES.md`

## 输出格式

```md
## LLM 调用层设计

### 调用场景
### Provider
### Prompt Version
### Input Schema
### Output Schema
### 错误处理
### 日志与脱敏
### 成本控制
### 人工确认边界
```

## 强制规则

1. 业务 Service 不直接调用 OpenAI SDK。
2. AI 输出默认建议，不自动执行高风险操作。
3. Prompt 必须有版本。

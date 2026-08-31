# Skill: Feature Slice Planner

## 用途

本 Skill 用于指导 AI 在开发一个功能或页面前，先明确任务边界，避免一次性生成过多代码。

## 必须读取

1. `AGENTS.md`
2. `docs/FEATURE_SLICE_DEVELOPMENT_RULES.md`
3. `docs/REQUIREMENT_TEMPLATE.md`
4. `docs/ACCEPTANCE_CRITERIA_RULES.md`

## 输出格式

```md
## 功能切片计划

### 任务理解
### 本次只做
### 本次不做
### 前端范围
### 后端范围
### API 契约草案
### 数据库影响
### Celery 影响
### old-system 是否参考
### 验收标准
### 风险点
```

## 强制规则

1. 一个任务只做一个功能。
2. 一个任务最多只做一个页面。
3. 如果范围过大，必须拆分任务。
4. 用户确认前不要修改代码。

# Skill: React Component Architect

## 用途

本 Skill 用于指导 AI 在开发 React 页面前，先设计组件拆分方案。

## 必须读取

1. `docs/UI_COMPONENT_CATALOG.md`
2. `docs/COMPONENT_AND_MODULE_RULES.md`
3. `docs/CODE_COMMENT_RULES.md`

## 输出格式

```md
## 组件拆分方案

### 页面职责
### 页面专属组件
| 组件 | 目录 | 职责 |
|---|---|---|
### 可复用组件
| 组件 | 是否已有 | 建议目录 | 说明 |
|---|---|---|---|
### Hooks
### API 封装
### 类型文件
### 不建议封装的内容
### 风险点
```

## 强制规则

1. 页面不能写成巨型文件。
2. API 请求不能直接写在页面中。
3. 类型不能散落。
4. 禁止把业务组件错误放入 common。
5. 禁止过度抽象一次性 UI。

# Skill: Code Review Checker

## 用途

本 Skill 用于指导 AI 在 PR 前进行自检。

## 必须读取

1. `docs/CODE_REVIEW_CHECKLIST.md`
2. `.github/pull_request_template.md`

## 输出格式

```md
## PR 自检报告

### 单功能确认

### old-system 确认

### 技术栈确认

### 组件与模块封装确认

### 注释确认

### 安全确认

### 测试确认

### 风险点

### 回滚方式
```

## 强制规则

如发现以下问题，AI 必须停止并提醒用户：

1. 修改了 `old-system/`。
2. 复制了旧代码。
3. 修改了 main/dev。
4. 提交了密钥。
5. 引入了未经确认的新依赖。
6. 一个 PR 做了多个无关功能。

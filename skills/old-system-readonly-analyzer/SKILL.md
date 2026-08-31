# Skill: Old System Readonly Analyzer

## 用途

本 Skill 用于指导 AI 只读分析 `old-system/`，提炼业务规则并设计新系统实现方案。

## 必须读取

1. `docs/OLD_SYSTEM_READONLY_RULES.md`
2. `docs/old-system-analysis/README.md`

## 输出格式

```md
## old-system 只读分析报告

### 本次读取文件
### 旧系统功能说明
### 旧系统数据来源
### 旧系统业务规则
### 旧系统存在的问题
### 新系统重建建议
### 应保留的业务规则
### 不建议延续的旧设计
### 是否需要用户确认
```

## 强制规则

1. 不修改 `old-system/`。
2. 不格式化 `old-system/`。
3. 不运行写数据库脚本。
4. 不复制旧代码到新系统。
5. 分析结果写入 `docs/old-system-analysis/`。

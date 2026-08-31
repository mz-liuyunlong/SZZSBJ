# Skill: Rule Pack Maintainer

## 用途

本 Skill 用于维护规则包，防止 AI 修改规则时制造重复、冲突和口径不一致。

## 必须读取

1. `RULE_PACK_FILE_INDEX.md`
2. `AGENTS.md`
3. 相关 docs 与 skills

## 输出格式

```md
## 规则包修改计划

### 需要修改的规则
### 主规则来源
### 需要同步的入口文件
### 冲突检查
### 删除/合并内容
### 变更摘要
```

## 强制规则

1. 同一规则只保留一个主来源。
2. 入口文件只引用，不制造不同标准。
3. 修改后必须更新 `RULE_PACK_FILE_INDEX.md` 和 changelog。

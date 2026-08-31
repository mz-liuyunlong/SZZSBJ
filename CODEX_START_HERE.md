# Codex 使用入口

## 文件用途

本文件是项目负责人使用 Codex 时的操作说明。它不是项目总规则；项目总规则是 `AGENTS.md`。

## 推荐启动提示词

```md
你现在参与本项目开发。

请先读取并遵守：
1. AGENTS.md
2. RULE_PACK_FILE_INDEX.md
3. docs/TECH_STACK.md
4. docs/FEATURE_SLICE_DEVELOPMENT_RULES.md
5. docs/OLD_SYSTEM_READONLY_RULES.md
6. docs/COMPONENT_AND_MODULE_RULES.md
7. docs/CODE_COMMENT_RULES.md
8. docs/API_CONTRACT_RULES.md

如果本次涉及页面开发，还必须读取：
- skills/feature-slice-planner/SKILL.md
- skills/react-component-architect/SKILL.md
- skills/page-acceptance-checker/SKILL.md

如果本次涉及后端，还必须读取：
- skills/backend-module-designer/SKILL.md

如果本次需要参考旧系统，还必须读取：
- skills/old-system-readonly-analyzer/SKILL.md
- skills/rebuild-mapping-planner/SKILL.md

请先输出：
1. 你读取了哪些规则文件
2. 当前分支和 git 状态
3. 本次任务范围
4. 组件拆分方案
5. 后端模块拆分方案
6. API 契约草案
7. 数据来源和字段血缘
8. 风险点
9. 测试方式

在我确认之前，不要修改代码。
```

## Codex 任务粒度

不要给 Codex 大任务。不要说“做完整广告模块”。应该说“本次只开发广告活动列表页面，建立必要的最小前后端闭环，不开发搜索词、否定词、调价记录等其他页面”。

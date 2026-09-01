# Project Rule Pack V1.0

这是新系统重建项目的 AI 工程治理规则包。

## 版本

```text
Rule Pack Version: V1.0
```

## 核心目标

```text
1. 防止 AI 乱改 old-system
2. 防止生产数据库、密钥、部署被误操作
3. 固定技术栈和目录结构
4. 固定导航、权限、API、SOP、测试标准
5. 用 PRP 做复杂功能施工图
6. 用 planning files 防止长任务丢失
7. 用 Context7 防止第三方库用法过期
8. 用 Playwright 做页面验收
9. 用 AI Skill Registry 管理外部 Skill
```

## 推荐阅读顺序

```text
AGENTS.md
AI_DAILY_RULES.md
CODEX_START_HERE.md
RULE_PACK_FILE_INDEX.md
docs/00_RULE_PACK_V1_0_OVERVIEW.md
docs/tools/AI_SKILL_REGISTRY.md
docs/tasks/FIRST_40_CODEX_TASKS.md
```

## 外部 Skill 定位

| Skill | 定位 |
|---|---|
| planning-with-files | 长任务持久计划 |
| context-engineering / PRP | 复杂功能施工图 |
| Context7 | 第三方库文档核对 |
| Playwright | 前端 E2E 验收 |
| Ponytail | 项目规则持续生效与工作流守卫 |
| Superpowers | AI 工作流增强 |
| Vercel Agent Skills | React/UI/文档审查辅助 |

所有外部 Skill 都不能覆盖 `AGENTS.md`。

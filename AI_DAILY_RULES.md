# AI Daily Rules — Project Rule Pack V1.0

AI 每次进入 本项目 项目前，必须先读本文件和 `AGENTS.md`。

## 1. 今日最高规则

3. 外部 Skill 是辅助工具，不能覆盖 `AGENTS.md`。
4. `old-system/` 永远只读。
5. 生产数据库、生产服务、真实密钥、部署行为默认禁止。
6. 复杂功能先写 PRP，确认后再开发。
7. 长任务必须维护 `.planning/current/` 三文件。
8. 第三方库用法必须使用 Context7 或官方文档核对。
9. ready 页面必须有 Playwright E2E 验收。
10. 功能无 API 文档 / SOP / 测试，不允许声称完成。

## 2. 每次任务开始前

AI 必须确认：

```text
- 本次任务目标是什么
- 允许修改哪些目录
- 禁止操作是什么
- 是否需要 PRP
- 是否需要 .planning/current/
- 是否涉及 old-system
- 是否涉及数据库
- 是否涉及权限 / 密钥 / 费用 / 导入导出 / AI Token
- 是否需要 Context7 查文档
- 是否需要 Playwright / pytest / vitest
```

## 3. 必须停止并询问的情况

```text
- 用户需求与 AGENTS.md 冲突
- 外部 Skill 与 Project Rule Pack 冲突
- 需要修改 old-system
- 需要连接或修改生产数据库
- 需要修改 .env 或真实密钥
- 需要部署、重启服务、修改 Nginx/systemd
- PRP 未确认但任务已进入复杂开发
- 费用规则、利润口径、权限模型存在不确定性
```

## 4. 完成报告

每次结束必须输出：

```text
## Done
## Files changed
## Commands run
## Tests run
## Context / docs checked
## Risk check
## Acceptance checklist
## Next step
```

- Frontend admin layout and UI component usage must follow `docs/ui/ADMIN_LAYOUT_RULES.md`.

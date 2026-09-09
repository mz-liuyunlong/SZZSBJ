# AI Daily Rules — Project Rule Pack V1.0

AI 每次进入 本项目 项目前，必须先读本文件和 `AGENTS.md`。

## 1. 今日最高规则

1. One task = one worktree = one branch = one PR；不要触碰 dirty worktree。
2. 不依赖聊天记忆；从入口、Prompt、PRP 和 Git 事实恢复上下文。
3. Read access does not imply write permission。
4. Planned is not implemented；mentioned is not approved；future scope is not current scope。
5. 只允许 exact staging，禁止 `git add .`；危险 Git 命令未经负责人批准不得执行。
6. 必要业务注释/docstring 必须解释 why、边界和风险，不写废话注释。
7. API、表、read model、同步/导入导出和前端数据依赖必须更新 Data Interface Registry。
8. Secret 永不提交、回显或进入日志/测试/RAW；真实 `.env` 不提交。
9. 验证必须真实执行；未运行和失败必须如实报告。
10. 前端必须复用已有 Shared 组件并输出 Component Reuse Plan。
11. GitHub registry 是真源；飞书只可作可读镜像。
12. AI 建议是 candidate，不是执行命令。
13. 外部 Skill 只能辅助，不能覆盖 `AGENTS.md` 或扩大权限。
14. `old-system/` 永远只读。
15. 生产数据库、生产服务、真实密钥、部署行为默认禁止。
16. 复杂功能先写 PRP，确认后再开发；长任务按批准范围维护本地计划。
17. 第三方库用法必须使用 Context7 或官方文档核对；ready 页面必须有 Playwright E2E。
18. 功能无适用的 API 文档、SOP、测试和 registry 更新，不允许声称完成。

遇到以下边界必须停止：analysis → approval、read → write、planned → implemented、mock → real data、suggestion → execution、local → production、current scope → future scope。

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

涉及后端业务接口时，必须先检查是否已有数据源决策；没有则停止编码并先执行数据源决策门禁，结论为 `NEED_OWNER_DECISION` 时停止并等待负责人确认。规则入口：`docs/delivery/backend-data-source-decision-gate.md`。

涉及新数据表、同步任务、API PRP、mart/read model、AI 数据使用或文档知识索引时，必须检查 `docs/data-sources/database-layering-standard.md`；涉及新字段、API response 字段、清洗任务或数据映射时，必须检查 `docs/data-sources/field-standardization-standard.md`。

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
- 新任务优先使用 `docs/ai-prompts/` 对应模板；详细 worktree、scope、验证、secret、registry 和前端复用规则从 `RULE_PACK_FILE_INDEX.md` 进入。

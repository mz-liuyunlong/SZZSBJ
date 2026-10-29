# AI CI First — 提交前验证与失败治理

本规则适用于 Codex、Cursor、Copilot 等所有 AI 代码贡献者。继承 AGENTS.md、AI_DAILY_RULES.md 和现有授权边界；它不授权直接修改主分支、生产环境、部署或其他任务文件。

## 1. 提交前门禁

- 一个任务一个 worktree、branch、PR；不得修改 dirty worktree 或顺手重构。
- 在工作区完成当前任务后，**推送 PR 前**从仓库根目录真实执行 `bash scripts/ci-preflight.sh all`；需要只执行某一模块时使用 `rules`、`backend` 或 `frontend`，并明确列出未执行的检查。涉及完整 PR 的最终验收应执行全部适用项。
- 脚本只检查，不自动格式化、不修改测试断言、不关闭 CI。失败时先修复本次修改文件，再重新运行检查。
- backend：`uv sync --frozen`、Ruff format/check、完整 pytest、import smoke；新增 pytest 文件应具有唯一模块名，不得与现有测试文件冲突。
- frontend：`npm ci`、已有 lint/typecheck/test/build、配置了则运行 Playwright E2E。不能以脚本不存在时的跳过假装执行成功；如新增必须项，需同时添加 package.json 脚本。
- 数据库、迁移、权限和外部 API：除通用检查外还需按现有 GitHub Actions 工作流运行相关隔离 PostgreSQL/Redis 集成测试，测试数据不得连接生产系统。
- 所有结果按命令写明 PASS、FAIL 或 NOT RUN 和原因。不得宣称“应该通过”或“已完成”冒充实测。

## 2. CI 失败闭环

1. 打开失败 Actions Run，识别最早实际失败的 Job/Step，读取原始日志和首个根因，不只看红色总状态。
2. 分类为 FORMAT/LINT、TEST-COLLECTION、TEST-ASSERTION、BUILD/TYPE、MIGRATION、ENV/INFRA，记录失败文件、规则、命令、日志链接。
3. 只改已批准范围内的根因，不得删除断言、滥用 skip、提高 timeout、关闭 Job、用 `|| true` 吞掉失败或修改无关文件。
4. 完成同一命令的本地复测、适用的全量预检后才能再次 push；若环境无法复现，PR 保持 Draft 并报告限制，禁止无依据反复 push。
5. 对环境偶发故障，需提供外部证据后才可重试失败 Job；不能将重试作为代码修复。
6. 同一根因反复失败时停止盲目提交，保留日志并升级人工审查；不得自动合并。

## 3. PR 和合并

- PR 描述提供预检执行环境、SHA、命令与结果、失败/跳过原因、风险、回滚步骤和 CI Run URL；CI 未全绿始终保持 Draft。
- 每次 push 都必须等待对应最新 SHA 的全部要求检查完成（不能沿用旧 SHA 成功结果），完成权限/迁移等人工审核后才可申请合并。
- 仓库管理员需要在 main Ruleset 中设置 required status checks，并选定必须的 CI Job；仅提交文档或脚本不能代替 GitHub 管理端门禁。
- 任何更改 branch protections / rulesets、直接合并、部署或生产写入都需要项目负责人另行授权。

## 4. 实用命令

```bash
# repo root
bash scripts/ci-preflight.sh rules
bash scripts/ci-preflight.sh backend
bash scripts/ci-preflight.sh frontend
bash scripts/ci-preflight.sh all
```

注意：本地缺少 uv、Node 24、Python 3.13、Playwright 系统依赖时，必须报告 NOT RUN 和环境差异，而不是宣称 PASS。自动修复限当前改动文件（例如 `uv run ruff format <files>`、`uv run ruff check --fix <files>`），然后再次运行完整检查。

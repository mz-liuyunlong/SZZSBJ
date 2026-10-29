# Validation and Testing Rules

## Purpose

要求所有验证结论可复现、与真实执行一致。

## Required Rules

- 先读取 `package.json`、`pyproject.toml`、README、CI 或现有脚本，再选择命令；不得发明命令。
- 每个报告逐项列出 command、result、failure reason、skipped reason。
- 未执行写 `Not run` 并说明原因；失败必须如实报告。
- 禁止用 “should pass” 冒充 “passed”，禁止删除断言、`.only`、`.skip` 或扩大 timeout 掩盖问题。
- `git diff --check`、精确 scope/status 检查是所有 PR 的基础要求。

## AI CI First Gate

- 规范入口：`docs/delivery/ai-ci-first-standard.md`。
- 统一检查入口：仓库根目录执行 `bash scripts/ci-preflight.sh all`，或按任务执行 `rules`、`backend`、`frontend`，未执行的项目必须如实记录。
- 代码格式、导入排序、测试模块命名冲突必须在 push 前发现；失败后先定位原始日志根因、修复当前任务范围、重新验证，禁止靠频繁 push 试错。
- CI 绿色必须属于当前最新 SHA；CI 未通过、测试未执行和环境阻塞时不允许声明完成。

## Task-Type Minimums

| Task | Minimum validation |
|---|---|
| docs-only | Markdown/链接/规则检查、`git diff --check`、scope check |
| frontend | 已有 lint/type/test/build；页面按要求做视觉和 E2E 验收 |
| backend | 已有 format/lint/type/test/import checks |
| database/migration | 上述后端检查、隔离 test DB、migration upgrade/downgrade/rollback 计划；禁止 production |
| sync/external API | mock/fixture 契约、幂等/重试/失败测试；真实环境需单独授权 |

## Completion Checklist

- [ ] 命令确实存在且运行环境已说明。
- [ ] 输出数量、警告和失败未省略。
- [ ] 未连接未授权数据库、服务器或外部 API。
- [ ] CI 与本地差异已说明。
- [ ] 测试数据遵守 `docs/TEST_DATA_AND_FIXTURE_RULES.md`。

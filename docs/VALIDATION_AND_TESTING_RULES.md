# Validation and Testing Rules

## Purpose

要求所有验证结论可复现、与真实执行一致。

## Required Rules

- 先读取 `package.json`、`pyproject.toml`、README、CI 或现有脚本，再选择命令；不得发明命令。
- 每个报告逐项列出 command、result、failure reason、skipped reason。
- 未执行写 `Not run` 并说明原因；失败必须如实报告。
- 禁止用 “should pass” 冒充 “passed”，禁止删除断言、`.only`、`.skip` 或扩大 timeout 掩盖问题。
- `git diff --check`、精确 scope/status 检查是所有 PR 的基础要求。

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

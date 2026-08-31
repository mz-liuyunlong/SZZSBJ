# AI Git 开发规则

## 分支规则

AI 开发前必须执行或要求用户执行：

```bash
git status
git branch
```

如果当前在 `main` 或 `dev`，不得直接修改。必须从 `dev` 新建任务分支：

```bash
git checkout dev
git pull origin dev
git checkout -b ai/YYYYMMDD-task-name
```

## 分支命名

建议：

```text
ai/YYYYMMDD-module-page
feature/task-name
fix/task-name
docs/task-name
```

示例：

```text
ai/20260831-ads-campaign-list
ai/20260831-products-list
ai/20260831-order-profit-page
```

## 提交规则

Commit 格式：

```text
type(scope): description
```

类型包括：

```text
feat, fix, docs, refactor, test, chore, db, style, perf, build, ci
```

示例：

```text
feat(ads): add campaign list page
fix(order): correct refund profit calculation
docs(ai): update old-system readonly rules
```

## 禁止

AI 禁止：

- 直接 push 到 main/dev
- force push
- reset hard
- clean -fd
- 一个分支做多个模块
- 一个 PR 混合功能、重构、依赖升级、格式化

## PR 目标

普通开发 PR 目标分支应为 `dev`，不要直接合并到 `main`。

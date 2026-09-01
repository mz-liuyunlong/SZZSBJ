# 测试规则

## 文件用途

本文件用于约束 AI 在本项目中如何设计、执行和汇报测试。

## 总原则

1. AI 不允许伪造测试结果。
2. 没有执行测试时，必须明确说明未执行原因。
3. 每个 PR 必须说明测试命令、结果和人工验收方式。
4. 一个页面一个功能也必须有最小验收检查。
5. 后端业务逻辑优先写 Service 测试。
6. 数据库查询优先写 Repository 或集成测试。
7. Celery 任务必须至少测试任务编排逻辑或 Service 逻辑。

## 前端测试 / 检查

建议根据项目配置逐步加入：

```bash
npm run lint
npm run typecheck
npm run build
npm run test:e2e
```

Playwright E2E 详细规则见 `docs/delivery/e2e-playwright-standard.md`。

如果使用 pnpm 或 yarn，以项目确认后的包管理器为准。

前端页面至少人工检查：路由、筛选、表格、分页、Loading、Empty、Error、权限状态。

## 后端测试 / 检查

建议逐步加入：

```bash
pytest
ruff check .
```

如果项目选择其他格式化和测试工具，以项目确认后的配置为准。

## 汇报模板

```md
## 测试结果

### 已执行

| 命令 | 结果 |
|---|---|
|  |  |

### 未执行

| 命令 | 原因 |
|---|---|
|  |  |

### 人工验收方式

1.
2.
3.
```

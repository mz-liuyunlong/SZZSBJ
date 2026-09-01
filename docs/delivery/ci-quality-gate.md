# CI 质量门禁规则

## 1. 总规则

```text
CI 不通过，不允许合并。
类型检查不通过，不允许继续开发下一个功能。
测试失败，不允许声称完成。
Alembic migration 未检查，不允许合并。
old-system 被修改，不允许合并。
发现 secret，不允许合并。
```

## 2. 检查项

| 检查 | 前端 | 后端 |
|---|---|---|
| 安装 | npm ci | uv sync |
| 格式 | prettier | ruff format --check |
| 静态检查 | eslint | ruff check |
| 类型检查 | tsc | pyright / mypy |
| 单元测试 | vitest | pytest |
| 构建/导入 | vite build | import check |
| 迁移检查 | - | alembic check |
| API 契约 | OpenAPI diff | OpenAPI diff |
| 安全 | secret scan | secret scan |
| 旧系统保护 | 禁止改 old-system | 禁止改 old-system |

## 3. 分阶段 CI

当前规则包阶段：

```text
检查规则文件存在
检查 old-system 保护
检查无明显密钥
```

前后端初始化后：

```text
frontend lint / typecheck / build / test
backend ruff / pyright / pytest / alembic check
```

## 4. PR 合并标准

PR 必须写清：

```text
改了什么
为什么改
影响哪些页面
影响哪些 API
是否影响数据库
是否影响权限
是否影响 old-system
测试结果
回滚方式
```

# 固定技术栈

## 1. 最终选型

| 层级 | 分类 | 选型 | 作用 |
|---|---|---|---|
| 前端 | 框架 | React | 构建页面和组件 |
| 前端 | 类型系统 | TypeScript | 类型安全和可维护性 |
| 前端 | 构建工具 | Vite react-ts | 创建、启动、构建前端项目 |
| 前端 | 包管理器 | npm | 前端依赖安装和脚本运行 |
| 前端 | UI 组件 | Ant Design | 基础 UI 组件 |
| 前端 | 高级组件 | ProComponents | ProTable、ProForm 等后台业务组件 |
| 前端 | 路由 | React Router | 页面跳转和菜单路由 |
| 前端 | 状态管理 | Zustand | 跨页面状态管理 |
| 前端 | 图表 | ECharts | 数据可视化 |
| 后端 | 语言 | Python 3.13 | 后端主语言 |
| 后端 | 依赖管理 | uv + pyproject.toml + uv.lock | Python 项目和依赖锁定 |
| 后端 | Web 框架 | FastAPI | API 服务 |
| 后端 | 数据校验 | Pydantic | 入参、出参、配置校验 |
| 后端 | ORM | SQLAlchemy 2 | 数据访问 |
| 后端 | 迁移 | Alembic | 表结构版本管理 |
| 后端 | 队列依赖 | Redis | Celery broker / result backend / cache |
| 后端 | 后台任务 | Celery | 同步、导入、导出、AI 等耗时任务 |
| 后端 | AI 调用 | LLM Provider Adapter | 统一封装模型供应商 |
| 数据库 | 新库 | PostgreSQL | 新系统数据库 |
| 数据库 | 旧库 | MySQL readonly | 旧系统只读数据源 |

## 2. 版本文件

初始化项目时应创建：

```text
.node-version      # 24
.python-version    # 3.13
```

## 3. 禁止事项

AI 不允许：

1. 把 React 改成 Vue / Next.js / Nuxt。
2. 把 Ant Design 改成其他 UI 框架。
3. 绕过 TypeScript，大量使用 `any`。
4. 把后端改成 Node.js / Express / NestJS。
5. 用 Poetry / requirements.txt 替代 uv，除非项目负责人批准。
6. 绕过 SQLAlchemy 到处写复杂裸 SQL。
7. 新增数据库字段但不写 Alembic migration。
8. 前端直接连接数据库。
9. 前端直接调用 OpenAI / Walmart / 领星等敏感 API。
10. 引入第二套后台任务系统。
11. 新建第二套 admin 系统。

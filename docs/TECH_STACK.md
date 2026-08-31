# 当前固定技术栈

## 文件用途

本文件定义本项目固定技术栈。任何 AI 不允许自行重新选型。

## 已确定技术栈

| 层级 | 分类 | 选型 | 作用 |
|---|---|---|---|
| 前端 | 前端框架 | React | 构建页面和组件 |
| 前端 | 类型系统 / 工程约束 | TypeScript | 提高可维护性和类型安全 |
| 前端 | 构建工具 / 脚手架 | Vite（react-ts） | 创建、启动、构建前端项目 |
| 前端 | 组件库 | Ant Design | 基础 UI 组件 |
| 前端 | 高级业务组件 | ProComponents | 后台表格、表单、查询页组件 |
| 前端 | 路由 | React Router | 页面跳转和菜单路由 |
| 前端 | 状态管理 | Zustand | 跨页面状态管理 |
| 前端 | 图表 | ECharts | 数据可视化 |
| 后端 | 后端语言 | Python | 后端主语言 |
| 后端 | Web 框架 | FastAPI | API 服务 |
| 后端 | 数据校验 | Pydantic | 入参、出参、配置校验 |
| 后端 | 数据库工具 | SQLAlchemy | ORM 数据访问 |
| 后端 | 数据库迁移 | Alembic | 表结构版本管理 |
| 后端 | 缓存 / 队列依赖 | Redis | 缓存、Celery Broker、任务状态 |
| 后端 | 后台任务队列 | Celery | 同步、批量、AI 等耗时任务 |
| 后端 | AI 调用层 | LLM Provider Adapter | 统一封装模型调用，避免业务代码绑定单一供应商 |
| 后端 | 默认模型 SDK | OpenAI Python SDK | 默认用于调用 OpenAI 模型 |

## 待项目负责人确认的工程选型

以下选型尚未在本规则包中固定，AI 不允许自行决定，必须先问项目负责人：

| 项目 | 说明 |
|---|---|
| 前端包管理器 | npm / pnpm / yarn 选一个 |
| Node 版本 | 建议 Node 20 LTS，但需确认 |
| Python 版本 | 建议 Python 3.11 或 3.12，但需确认 |
| 后端依赖管理 | uv / Poetry / requirements.txt 选一个 |
| 数据库类型 | PostgreSQL / MySQL / SQLite / 其他，需确认 |
| 代码格式化 | 前端 ESLint + Prettier；后端 Ruff / Black，需确认细节 |
| API 返回格式 | 需统一定义 |
| 分页规范 | 默认建议 page / page_size，需确认 |
| 时间规范 | 默认建议数据库 UTC，前端按业务时区展示，需确认 |
| 金额规范 | 默认建议字段带币种后缀，如 `_usd`、`_cny` |

## 禁止事项

AI 不允许：

1. 把 React 改成 Vue / Next.js / Nuxt。
2. 把 Ant Design 改成其他 UI 框架。
3. 绕过 TypeScript，大量使用 `any`。
4. 把后端改成 Node.js / Express / NestJS。
5. 绕过 SQLAlchemy 到处写复杂裸 SQL。
6. 新增数据库字段但不写 Alembic migration。
7. 前端直接连接数据库。
8. 前端直接调用 OpenAI / Walmart / 领星等敏感 API。
9. 引入第二套后台任务系统。
10. 新建第二套架构。

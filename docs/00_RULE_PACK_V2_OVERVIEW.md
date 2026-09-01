# SZZSBJ Rule Pack v2.0 总览

## 1. v2 优化目标

本规则包用于指导 SKYC V2 企业级运营数据系统从零重建。v2 的目标不是增加更多业务功能，而是把规则收敛成可执行标准：

```text
AI 能读懂
Codex 能执行
项目负责人能验收
多人协作不会乱
系统后期能追溯、能审计、能回滚
```

---

## 2. 规则分层

```text
第 1 层：强制入口规则
- AGENTS.md
- AI_DAILY_RULES.md
- RULE_PACK_FILE_INDEX.md

第 2 层：工程架构规则
- docs/architecture/
- docs/database/

第 3 层：业务口径规则
- docs/business-rules/

第 4 层：交付验收规则
- docs/delivery/
- docs/tasks/

第 5 层：运维发布规则
- docs/operations/
```

旧 `docs/*.md` 文件仍保留，作为细分参考。若旧文件和 v2 新文件冲突，以 v2 新文件为准。

---

## 3. P0 / P1 / P2 优先级

### P0：第一阶段必须完成

```text
1. 前端导航壳和占位页面
2. navigation.ts 配置驱动
3. PageShell 统一页面外壳
4. 右上角 ? 帮助入口
5. 数据中心 > API文档 页面
6. 后端统一 API 返回格式
7. PostgreSQL 初始核心表
8. Alembic 迁移框架
9. 用户 / 角色 / 权限基础
10. 数据权限字段预留
11. 组织架构字段预留
12. 费用规则版本化
13. 集成配置和密钥安全管理
14. CI 基础检查
15. old-system 只读保护
16. Codex 第一批任务队列
```

### P1：第二阶段尽快补

```text
1. 数据质量
2. 指标字典
3. 数据血缘
4. 审批流
5. 通知中心
6. 导入导出回滚
7. 字段级权限
8. 导出水印
9. AI 成本统计
10. 数据新鲜度 SLA
```

### P2：后期扩展

```text
1. 数据血缘可视化
2. 复杂多级审批流
3. 培训中心
4. 用户反馈中心
5. 高级灰度发布
6. 规则冲突检测中心
7. AI 建议采纳效果闭环
```

---

## 4. 已锁定的项目决策

| 决策 | 结果 |
|---|---|
| 数据库 | PostgreSQL |
| 旧库 | MySQL 只读引用，不写、不改、不全量复制 raw 大表 |
| 后端 | Python 3.13 + FastAPI + uv |
| 前端 | React + TypeScript + Vite + Ant Design + ProComponents |
| API 格式 | `{ success, data, error, meta, request_id }` |
| API 文档 | 数据中心 > API文档，仅授权可见 |
| SOP | 每个页面右上角 ?，新标签页打开对应文章 |
| 权限 | 角色动态配置，代码只认 permissionKey |
| 数据权限 | 每个页面单独配置，可选 all / own / team / selected 等 |
| 组织架构 | 支持小组长、组员、部门、直属关系 |
| 费用规则 | 版本化 + 生效日期 + 失效日期 + 审批 + 审计 |
| 集成配置 | 设置 > 系统配置 > 集成配置，Token 加密脱敏 |
| 后台管理 | 不新增第二套后台系统，复用设置和数据中心 |

---

## 5. 第一阶段落地顺序

```text
1. 创建 SKYC_V2_REBUILD 总目录
2. 放入本规则包
3. 建立 AGENTS.md / docs / .github / scripts
4. 初始化 frontend Vite react-ts
5. 初始化 backend FastAPI + uv
6. 创建 PostgreSQL 本地库和 Alembic 框架
7. 创建 navigation.ts + MainLayout + PageShell + ComingSoon
8. 创建 API Response 标准和 OpenAPI 基础
9. 创建权限 / 组织架构 / 费用规则 / 集成配置核心表 migration 草稿
10. 创建数据中心 API文档占位页面
11. 创建页面右上角帮助入口
12. 进入第一个真实只读页面开发
```

---

## 6. 禁止第一阶段做的事

```text
不要重写所有旧页面
不要全量复制旧库 raw 大表
不要接真实外部平台 API
不要上线生产
不要做第二套 admin 系统
不要做复杂审批流
不要做复杂数据血缘可视化
不要让普通用户看到 API 文档
不要让前端拿到任何 Token
```

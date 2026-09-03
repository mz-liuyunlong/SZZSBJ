# 运营数据中台（lingxing-auto）

跨境电商（Walmart 为主）运营数据中台 + Admin 后台 + AI 自动化。目标：提单、提利润、提效率，用 AI 自动化降人力。

> 本文件是仓库入口说明。系统全貌请按「context 阅读顺序」读 context/ 四份主文档——那里才是权威。
> （历史注：本仓库最初是"领星 API 最小连接测试"，早已演进为完整中台，旧 README 已于 2026-07-31 重写。）

## 当前定位

- **数据中台**：领星 API / 飞书 / Walmart 广告 → MySQL `walmart_ai_data`，强制分层（唯一权威定义见 `context/PROJECT_CONTEXT.md`「数据分层与 AI 边界」，此处不复述）。
- **Admin 后台**（:3001，React + Express）：运营中心（看板/销售明细/产品管理/运营日志/目标管理/经营分析/清货中心）、广告系统、智能PMC、AI人力（绩效/日志评级/考勤/花名册）、AI工具（会议分析/LLM切换/API文档/帮助中心）。统一登录 SSO（app_session JWT）。
- **AI 自动化**：约 49 条 crontab（同步链/构建链/通知链/周报月报/考勤/AI周评），飞书卡片交互（审批/确认/催办）。
- **对外只读**：internal-readonly API（同事）、Custom GPT 经营分析（经海外中转+SSH隧道）。

## 目录说明

- `src/` 后端：adminServer.ts(聚合入口) + 各业务路由(*Routes.ts) + 同步/通知脚本(sync*/notify*/build*) + apiKeyManager.ts(:3456 独立服务)
- `admin-frontend/` 前端（Vite+React，构建产物 dist/ 由 admin 静态托管）
- `sql/` 数据库迁移（编号递增，幂等；新表必须登记 DATABASE_MAP「唯一写入方」）
- `context/` **系统文档真源**（单写入方=本仓库；生产副本为只读镜像）
- `scripts/` 运维/回填脚本 ｜ `tests/` 测试 ｜ `_bak/` 历史备份隔离区（勿读作现状）

## 启动

- 后端：`npm run admin:server`（= npx ts-node src/adminServer.ts，端口 3001）
- 前端：`cd admin-frontend && npm run dev`；构建 `npm run build`（⚠️ Mac 缺 rollup 原生依赖，生产构建在服务器做）
- 常用脚本见 package.json scripts（sync:*/notify:*/build:*，多数默认 dry-run，`--send`/`--confirm-write` 才真跑）

## 生产组成（42.193.254.170）

systemd：`lingxing-admin`(:3001) / `lingxing-api-key-manager`(:3456) / `ads-ai-api` / `asin-kw-backend`(:8000) / `gpt-api-tunnel`；另 :3000 广告 Next.js、:8081 会议分析。定时任务权威清单：context/PIPELINE_MAP.md 文末 Active cron snapshot。

**部署流程**：本仓库(Mac)=代码真源 → 部署 AI 按 context/CODE_DEPLOY_SOP.md 白名单 scp + md5 对账 + 重启验收。生产不 git pull。

## context 阅读顺序（新任务开工前必读）

1. `context/PROJECT_CONTEXT.md` — 定位/铁律/风险基线/制度
2. `context/SYSTEM_MAP.md` — 模块视图（开头总览表）
3. `context/DATABASE_MAP.md` — 表结构/唯一写入方/人工字段保护
4. `context/PIPELINE_MAP.md` — 任务编排 + cron 快照
5. 打底：`context/TASK_CHANGE_LOG.md`（变更史）、`context/UI_STANDARDS.md`（前端规范）、`context/CODE_DEPLOY_SOP.md`（部署）

## 高风险约束（红线）

1. 改前核查代码与真实表结构，禁止臆测字段/接口/环境变量。
2. 禁删原有功能；无明确指令不得改 crontab/systemd/生产定时任务。
3. 密钥只读环境变量，严禁硬编码；文档/日志不落密钥明文。
4. 前端/GPT 禁止直查 RAW；AI 只写 AI 层；不可覆盖运营人工记录、不删历史、不清表。
5. 新功能隔离开发，最小改动旧页面；高风险变更先标风险+替代方案；改动配套测试命令+验收标准。

# 第一批 30 个 Codex 任务队列

## Phase 0：规则包落地

### 01 安装规则包
- 允许修改：项目根目录规则文件
- 输出：AGENTS.md、docs、skills、.github、scripts
- 验收：规则文件完整，old-system 只读说明存在

### 02 初始化 Git 规则
- 允许修改：.github、CODEOWNERS、PR template、CI
- 验收：CI 至少检查规则文件和 old-system 保护

### 03 写入项目决策日志
- 允许修改：docs/01_PROJECT_DECISIONS.md
- 验收：关键决策完整记录

## Phase 1：前端壳

### 04 初始化 frontend
- 命令：npm create vite@latest frontend -- --template react-ts
- 验收：React TS 项目启动成功

### 05 安装前端依赖
- 依赖：antd、@ant-design/pro-components、react-router-dom、@tanstack/react-query、zustand、echarts、echarts-for-react
- 验收：package.json 正确

### 06 创建 navigation.ts
- 输入：docs/business-rules/navigation-spec.md
- 验收：完整一级/二级导航、API文档、help字段

### 07 创建 MainLayout / PageShell / ComingSoon
- 验收：所有页面可点击进入占位页

### 08 创建帮助入口
- 验收：PageShell 右上角 ? 新标签页打开 helpUrl

### 09 创建数据中心 API文档占位页
- 验收：权限点 data_center.api_docs.view，页面占位

## Phase 2：后端壳

### 10 初始化 backend
- 命令：uv init / FastAPI 项目结构
- 验收：app/main.py 可启动

### 11 创建统一 response.py
- 验收：ApiResponse 支持 success/data/error/meta/request_id

### 12 创建 config.py
- 验收：读取 local/staging/production 配置，不含真实密钥

### 13 创建 PostgreSQL session
- 验收：本地连接配置通过 .env.example 定义

### 14 创建 legacy_mysql readonly session
- 验收：只读连接模块，不执行写操作

### 15 创建 Alembic 框架
- 验收：alembic 可生成迁移草稿

## Phase 3：核心表

### 16 创建权限表 migration 草稿
- 表：sys_user、sys_role、sys_permission、sys_user_role、sys_role_permission

### 17 创建页面数据权限表 migration 草稿
- 表：sys_page_data_scope

### 18 创建组织架构表 migration 草稿
- 表：org_unit、org_user_membership、org_user_report_line

### 19 创建产品负责人表 migration 草稿
- 表：core_product_owner

### 20 创建费用规则表 migration 草稿
- 表：biz_fee_rule、finance_period_lock

### 21 创建密钥和集成配置表 migration 草稿
- 表：sys_secret、sys_secret_version、sys_integration_config

### 22 创建审计日志表 migration 草稿
- 表：audit_action_log、audit_permission_change_log、audit_secret_change_log

## Phase 4：契约与文档

### 23 创建 API 文档规范模板
- 输出：docs/api/README.md

### 24 创建 SOP 模板
- 输出：docs/sop/README.md

### 25 创建 API 文档页面读取 /openapi.json 的 mock 实现
- 验收：能显示 mock 接口列表

### 26 创建权限中间件草稿
- 验收：require_permission 接口存在

### 27 创建数据权限过滤草稿
- 验收：apply_data_scope 接口存在

### 28 创建集成配置页面占位
- 位置：设置 > 系统配置 > 集成配置
- 验收：只显示占位，不保存真实 Token

### 29 创建费用规则页面占位
- 位置：设置 > 费用规则
- 验收：说明版本化、生效日期、影响预览

### 30 汇总交接文档
- 输出：CODEX_HANDOFF.md
- 验收：完成内容、未完成内容、风险、下一步明确

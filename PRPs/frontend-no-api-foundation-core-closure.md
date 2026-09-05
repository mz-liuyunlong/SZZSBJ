# Frontend No-API Foundation Core Closure PRP

## 1. Title

Frontend No-API Foundation Core Closure

目标文件：

`PRPs/frontend-no-api-foundation-core-closure.md`

## 2. Status

**Approved**

本 PRP 已由负责人正式批准为总 PRP。

批准范围：

- 允许将本 PRP 以 `Approved` 状态随 Gate 1 PR 入库。
- 允许 Gate 1 单独进入执行准备。
- Gate 2–5 尚未授权实现。
- 禁止将本 PRP 理解为五个 Gate 的连续实施授权。
- 每个 Gate 仍需负责人单独确认并单独下发工程师执行 Prompt。

批准后的执行规则：

1. PRP 状态已改为 `Approved`。
2. 每个 Gate 仍需负责人单独确认。
3. 每个 Gate 仍需单独下发工程师执行 Prompt。
4. 每个 Gate 必须单独分支、测试、审查和 PR。
5. 前一个 Gate 合并并同步最新 `main` 后，才能开始下一个 Gate。
6. 为避免形成第六个 PR，已批准的总 PRP 默认随 Gate 1 PR 入库。

总 PRP `Approved` 不等于允许一次性或连续实现全部五个 Gate。

## 3. Owner Confirmations

负责人已经确认：

1. 采用一个总 PRP、五个执行 Gate。
2. 不允许合并成一个超级 PR。
3. 不机械拆成 NF-01 至 NF-09。
4. 不为每个小组件单独建立任务。
5. 每个 Gate 独立分支、独立 PR、独立测试、独立审查、独立回滚。
6. 每个 Gate从当时最新 `main` 创建。
7. 前一个 Gate 合并并同步 `main` 后，才能开始下一个 Gate。
8. 当前集成基线是 `main`，不再默认从 `dev` 创建功能分支。
9. Routing Foundation 可以优先于 FIRST\_40 原顺序中的 PageShell、ComingSoonPage 和 LegacyPageWrapper。
10. Routing-first 是负责人批准的受控顺序调整。
11. LegacyPageWrapper 本轮延期。
12. 本轮不读取、不包装、不迁移 old-system 页面。
13. 本轮不接真实 API、真实认证、真实权限、后端或数据库。
14. 工程师默认禁止执行上传与提交操作。
15. 负责人本人负责暂存、提交、上传、PR、合并和分支清理。
16. 普通刷新可以保留合法 Tab workspace，但 mock 登录态必须丢失。
17. 重新 mock 登录后恢复合法 Tabs。
18. 主动退出必须清除 Tab workspace。
19. 主动退出后重新登录只进入默认首页 Tab。
20. sessionStorage 只允许保存 path-only Tab workspace schema。
21. ForgotPassword 是前端 mock 流程，不会真实发送飞书卡片。
22. PageShell 不向普通用户显示 `permissionKey`。
23. 首页 Tab 固定且不可关闭。
24. Tab 最大数量为 12。
25. 超过 12 个时提示用户关闭旧 Tab，不自动淘汰。
26. KeepAlive 测试 fixture 只能存在于测试文件中。

## 4. Executive Summary

本 PRP 规划前端 no-API 基础闭环，在不连接真实 API、后端、数据库或真实认证系统的前提下，分五个 Gate 建立：

1. Routing Foundation
2. Auth Routes
3. Page Foundation
4. Error Shell
5. Tab Lifecycle

总体目标：

- 使用 Hash Router 建立 URL 驱动的 active page。
- 从 `navigation.ts` 派生统一合法路由判断。
- 将现有 mock 登录纳入路由。
- 建立最小 AuthLayout 和 ForgotPasswordPage。
- 建立最小 PageShell 和唯一 ComingSoonPage。
- 建立静态 404、ErrorBoundary 和 500 fallback。
- 建立 path-only Tab Restore。
- 建立最小 Tab KeepAlive 生命周期。
- 固定首页 Tab。
- 将最大 Tab 数量限制为 12。
- 保持 `navigation.ts` 为导航和页面 metadata 单一来源。

本 PRP 不允许：

- 一个 PR 实现全部内容。
- 跨 Gate 顺手实现。
- 为未来需求提前搭建通用框架。
- 通过增加依赖解决现有平台能力可以完成的问题。

## 5. Current State

当前前端已经具备：

- React + TypeScript + Vite
- Ant Design + ProComponents
- React Router 依赖
- mock 登录页
- MainLayout
- 一级导航
- 二级 flyout
- Breadcrumb
- Tabbar
- Content 占位区
- TopbarActions
- mock 用户、通知和退出流程
- `frontend/src/config/navigation.ts` 导航元数据

当前以下状态仍主要由 `App.tsx` 和 `MainLayout.tsx` 的本地 state 管理：

- mock 登录状态
- active page
- open tabs
- Breadcrumb
- Content 切换

五个 Gate 将逐步收敛这些状态，不允许一次性重写全部状态流。

## 6. Goals

1. URL 成为 active page 的权威来源。
2. 使用 Hash Router 支撑当前静态部署。
3. 建立统一 route resolver。
4. LoginPage 使用 `/login`。
5. AuthLayout 复用认证页面品牌区。
6. ForgotPasswordPage 提供明确标注的 mock 流程。
7. 建立最小 PageShell。
8. 建立唯一 ComingSoonPage。
9. 建立静态 404。
10. 建立 ErrorBoundary 和 500 fallback。
11. 使用 sessionStorage 恢复 path-only Tab workspace。
12. 普通刷新后先回登录，重新登录后恢复 Tabs。
13. 主动退出清除 Tab workspace。
14. 当前会话切换 Tab 时保留页面组件状态。
15. 关闭 Tab 时销毁对应页面组件状态。
16. 刷新后页面内部状态回到初始状态。
17. 首页 Tab 固定且不可关闭。
18. 最多打开 12 个 Tab。
19. 每个 Gate 独立测试、审查、回滚。
20. 不复制 navigation metadata。

## 7. Non-goals

本轮明确不做：

- 真实登录 API
- 真实退出 API
- `/auth/me`
- `/auth/logout`
- 真实 token
- 真实 cookie session
- CSRF 接入
- 真实权限系统
- 真实 route permission guard
- 真实飞书密码重置
- 真实飞书卡片
- 用户存在性查询
- 真实通知 API
- 真实 AI API
- 真实业务 API
- 后端开发
- 数据库连接
- 数据库表或迁移
- old-system 页面读取、包装、嵌入或迁移
- Vercel rewrite
- Vercel 配置修改
- CI 修改
- 新增或升级依赖
- Playwright E2E 实现
- LegacyPageWrapper
- ListPageShell
- FormPageShell
- Dirty Form Guard
- Debug Panel
- 权限开发面板
- Tab 右键菜单
- Tab 批量关闭
- Tab 右键刷新
- Tab 固定/取消固定
- LRU Tab 淘汰
- 自动关闭旧 Tab
- 全局搜索
- 最近访问
- 收藏页面
- 主题切换
- 页面标题与浏览器标题同步
- 前端版本信息
- 开发环境 Banner
- 真实业务页面
- 生产测试页面
- 测试专用 navigation metadata

## 8. Architecture Decisions

### 8.1 Hash Router

本任务采用 Hash Router。

原因：

- 当前前端采用静态部署。
- 不修改 Vercel rewrite。
- Hash Router 可避免直接刷新业务路径时依赖服务端 rewrite。
- 项目已经安装 React Router，不需要新增依赖。

如果以后需要干净 URL，BrowserRouter 迁移必须单独评估。

### 8.2 Routing-first 受控调整

Routing Foundation 优先于 FIRST\_40 原顺序中的：

- PageShell
- ComingSoonPage
- LegacyPageWrapper

原因：

- URL 状态源影响 PageShell、Tab Restore 和 KeepAlive。
- 先确定路由可以减少后续返工。

这是负责人明确批准的受控调整。

不得借此：

- 大范围重写 FIRST\_40
- 更改无关任务顺序
- 提前实现后续 Gate
- 弱化一个任务一个 PR 的规则

### 8.3 `main` 为集成基线

项目实际流程：

- 功能分支从最新 `main` 创建。
- GitHub PR 合并到 `main`。
- Vercel Production 跟随 `main`。
- 本地主目录保持干净 `main`。
- 前一个 Gate 合并后，负责人同步 `main`，再创建下一个 Gate 分支。

如现有 Git 文档仍要求从 `dev` 创建分支，仅允许进行与当前流程直接相关的最小规则同步。

### 8.4 LegacyPageWrapper 延期

项目当前是 greenfield。

本轮不实现 LegacyPageWrapper。

只有以后确实需要嵌入、跳转或桥接 old-system 页面时，才允许单独评估。届时必须重新确认：

- old-system 只读边界
- 是否需要 PRP
- 安全与权限边界
- 新旧系统耦合风险

### 8.5 URL 为 active page 权威来源

必须保证：

- 菜单点击更新 URL。
- Tab 点击更新 URL。
- 浏览器前进/后退同步 active page。
- Breadcrumb、Tabbar 和 Content 从当前 URL 派生。
- MainLayout 不再维护与 URL 竞争的 activePath 权威状态。
- Tab workspace 只能记录打开路径和顺序，不能覆盖 URL 的 active page 决策。

### 8.6 统一 Route Resolver

必须建立一个从 `navigation.ts` 派生的最小 route resolver。

统一负责：

- path 查找
- route eligibility
- 当前页面 metadata
- Breadcrumb metadata
- Tab metadata 恢复
- hidden/disabled/unknown 判断

基本语义：

- ready/enabled 业务页面可进入。
- hidden 页面不显示在 Sidebar，但可以由项目明确入口或合法 path 打开。
- disabled 页面不可直达、不可加入 Tab。
- unknown path 在 Gate 4 合并后进入 404。
- Gate 1 临时阶段允许回退到默认业务入口。
- 临时回退必须能被 Gate 4 独立替换。

Route resolver 必须被以下位置复用：

- Router
- Breadcrumb
- Tab Restore
- Tab eligibility 检查

禁止：

- 在 Router、MainLayout、PageShell、Tab workspace 中各自实现过滤规则。
- 复制完整 navigation metadata。
- 建立第二套 path/title/status/help/permission 配置。
- 把 resolver 扩展成无实际消费者的通用框架。

如果现有 navigation metadata 无法表达上述语义，工程师必须停止并报告，不得自行修改配置。

### 8.7 Tab Workspace 单一状态所有者

Gate 5 只能选择一个 Tab workspace 状态所有者。

默认优先采用与现有 MainLayout 相邻的最小专用 hook/module。

只有在执行前证明现有复杂度确实需要时，才考虑复用已经安装的 Zustand。不得为了“以后可能需要”引入 Store。

禁止同时维护：

- MainLayout openTabs state
- 独立 Tab Store openTabs state
- Router 内另一份 openTabs state

URL 负责 active page；Tab workspace owner 负责 open paths 和顺序。

## 9. Navigation Metadata Single-Source Rule

`frontend/src/config/navigation.ts` 必须继续作为以下信息的单一来源：

- 一级导航
- 二级导航
- title
- path
- permissionKey
- status
- help
- tabs
- children
- Breadcrumb 所需 metadata

禁止在以下位置维护第二套 metadata：

- Router
- MainLayout
- PageShell
- Tab workspace
- Error Shell
- Auth Routes
- mock 文件

恢复 Tabs 时，必须通过 path 从 `navigation.ts` 重新解析：

- title
- Breadcrumb
- icon
- help
- status
- 其他展示 metadata

## 10. Mock Auth and Storage Security Rules

### 10.1 Mock 登录态

mock 登录态只允许存在于当前运行时内存。

不得持久化：

- password
- token
- role
- permission
- auth boolean
- 完整用户对象
- 真实登录态
- 输入的真实姓名

普通刷新后：

1. mock 登录状态丢失。
2. 用户先进入登录页。
3. 合法 Tab workspace 可以继续保留。
4. 用户重新 mock 登录后恢复合法 Tabs。
5. 页面内部状态回到初始值。

### 10.2 主动退出

主动点击退出代表用户明确结束当前工作会话。

主动退出必须：

- 清除运行时 mock auth。
- 清除 mounted page。
- 清除 sessionStorage Tab workspace。
- 关闭当前菜单、弹层或遮罩。
- 返回登录页。

主动退出后重新登录：

- 不恢复旧 Tabs。
- 只进入默认首页 Tab。
- active page 为默认首页。
- 不留下废弃 storage key。

### 10.3 sessionStorage Schema

持久化结构必须等价于以下最小 schema：

```
type TabWorkspaceStorage = {
  version: number
  openPaths: string[]
  activePath: string
}
```

规则：

- `openTabs` 可以作为运行时 UI state 名称。
- sessionStorage 只保存有序 `openPaths`。
- 数组顺序即 Tab order，不重复保存另一份排序结构。
- `activePath` 必须属于恢复后的合法 `openPaths`。
- 默认首页 path 必须存在。
- 数据恢复前必须进行结构和路径校验。
- JSON 损坏时安全回退到默认首页。
- schema version 不支持时安全回退。
- 恢复时重新从 `navigation.ts` 解析展示 metadata。

禁止保存：

- title
- icon
- Breadcrumb
- help
- permissionKey
- status
- 完整 navigation item
- 用户对象
- role
- permission
- token
- auth boolean
- 页面组件 state
- 筛选条件
- 分页
- 滚动位置
- 表单草稿
- API 数据
- 缓存响应
- React 组件实例

## 11. Gate Dependency Diagram

```
Gate 1: Routing Foundation
        ↓
Gate 2: Auth Routes
        ↓
Gate 3: Page Foundation
        ↓
Gate 4: Error Shell
        ↓
Gate 5: Tab Lifecycle
```

执行规则：

- 一个总 PRP。
- 五个独立执行 Gate。
- 一个 Gate 一个分支、一个 PR。
- 每个 Gate 单独负责人确认。
- 每个 Gate 单独下发执行 Prompt。
- 每个 Gate 独立测试、审查、回滚。
- 前一个 Gate 合并并同步最新 `main` 后才能开始下一个 Gate。
- 不得从未合并的前序功能分支继续开发。
- 不得并行实现互相依赖的 Gate。
- 不得跨 Gate 顺手实现。

## 12. Global Scope Restrictions

所有 Gate 均禁止修改或接入：

- `backend/**`
- `old-system/**`
- `.github/**`
- `.env*`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/vite.config.ts`
- Vercel 配置
- CI 配置
- 数据库文件
- Alembic 文件
- 生产配置
- 真实 API client
- 真实 auth service
- 真实 permission store
- 无关业务页面
- 无关 CSS
- 无关 docs
- 真实密钥、Token 或密码

不得：

- 新增依赖
- 升级依赖
- 运行 `npm install`
- 运行 `npm update`
- 运行 `npm audit fix`
- 调用真实外部 API
- 连接数据库
- 修改或运行 old-system
- 建立第二套路由或导航配置
- 创建生产测试页面
- 创建测试专用正式 route
- 修改 navigation metadata 仅为测试服务

`frontend/dist/**` 不得暂存或提交。构建生成的忽略文件不属于源代码改动。

## 13. Gate 1 — Routing Foundation

### 13.1 Branch

`feat/frontend-routing-foundation`

### 13.2 Dependency

无。

必须从当时最新 `main` 创建。

### 13.3 Goal

使用项目现有 React Router 建立 URL 驱动的前端路由基础和统一 route resolver。

### 13.4 In Scope

- 在应用根部挂载 Hash Router。
- 为现有登录入口提供 `/login`。
- 建立统一 route resolver。
- 为 navigation 中可进入的页面提供统一路由解析。
- 一级/二级菜单点击更新 URL。
- Tab 点击更新 URL。
- 浏览器前进/后退同步 UI。
- 未登录访问业务 path 时进入 `/login`。
- mock 退出后进入 `/login`。
- URL 驱动 active page、Breadcrumb、Tabbar 和 Content。
- 使用现有 MainLayout Content 占位逻辑作为临时页面内容。
- Gate 1 未知业务 path 临时回退默认业务入口。
- 将已批准的总 PRP 文件纳入 Gate 1 PR。

### 13.5 Temporary Rendering Strategy

Gate 1 只负责 Routing。

在 Gate 3 之前：

- 继续复用现有 MainLayout Content 占位逻辑。
- route resolver 只把当前合法页面同步给现有 Content 区域。
- 不实现 ComingSoonPage。
- 不实现 PageShell。
- 不为每个 navigation item 创建临时页面。
- 不新增多个占位页面文件。

Gate 3 将负责正式统一 ComingSoonPage。

### 13.6 Out of Scope

- Tab Restore
- sessionStorage
- KeepAlive
- PageShell
- ComingSoonPage
- AuthLayout
- ForgotPasswordPage
- 404 页面
- ErrorBoundary
- 500 fallback
- 真实业务页面
- 真实权限判断
- Vercel rewrite
- 新依赖

### 13.7 Allowed Files

- `PRPs/frontend-no-api-foundation-core-closure.md`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/App.test.tsx`
- `frontend/src/layouts/MainLayout.tsx`
- `frontend/src/layouts/MainLayout.test.tsx`
- `frontend/src/router/routes.tsx`
- `frontend/src/router/routes.test.tsx`
- `frontend/src/router/routeResolver.ts`
- `frontend/src/router/routeResolver.test.ts`

允许进行最小文档同步：

- `docs/01_PROJECT_DECISIONS.md`
- `docs/architecture/frontend.md`
- `docs/AI_GIT_DEV_RULES.md`

文档仅允许记录：

- HashRouter 决策
- URL 权威状态源
- route resolver 单一入口
- `main` 集成基线
- Routing-first 受控调整

### 13.8 Forbidden Files

除全局禁止范围外，本 Gate 禁止修改：

- `frontend/src/config/navigation.ts`
- `frontend/src/pages/**`
- `frontend/src/components/**`
- Auth 页面结构
- Tab workspace 模块
- Error Shell 文件
- 无关文档

如 route resolver 无法从现有 navigation metadata 派生，必须停止并报告。

### 13.9 Tests

至少覆盖：

- `/login`
- 默认业务入口
- 菜单点击改变 hash
- Tab 点击改变 hash
- 浏览器前进/后退同步 active page
- Breadcrumb 同步
- Tabbar 同步
- Content 同步
- 未登录业务路径进入登录页
- mock 退出进入登录页
- unknown path 临时回退默认入口
- disabled path 不可进入
- hidden 合法 path 可按规则进入
- route metadata 来自 `navigation.ts`
- 不发送网络请求
- 不写入认证信息

### 13.10 Manual Acceptance

至少检查：

- 登录页正常。
- 默认业务入口正常。
- 一级和二级导航行为没有回归。
- 菜单、Tab、Breadcrumb、Content 与 hash 同步。
- 浏览器前进/后退同步。
- 退出回到登录页。
- 无 body/window 异常滚动。
- 刷新 hash 路径不会依赖 Vercel rewrite。
- 未提前出现 PageShell 或 ComingSoonPage。

### 13.11 Rollback Boundary

回滚 Gate 1 后：

- 恢复当前内存 active page 行为。
- MainLayout、LoginPage 和 TopbarActions 继续工作。
- navigation metadata 不受影响。
- 不留下未使用的 route resolver 或 Router 配置。

### 13.12 Definition of Done

- Hash Router 接入。
- URL 成为 active page 权威来源。
- route resolver 为唯一合法路径判定入口。
- MainLayout 现有占位内容继续工作。
- 测试、lint、build、diff-check 通过。
- 未实现 Gate 2–5 内容。
- 未修改禁止文件。
- 总 PRP 已处于 `Approved` 后才纳入 PR。

## 14. Gate 2 — Auth Routes

### 14.1 Branch

`feat/frontend-auth-routes`

### 14.2 Dependency

Gate 1 已合并，负责人已同步最新 `main`，并单独批准 Gate 2。

### 14.3 Goal

完成前端 mock 认证页面路由壳，不接真实认证。

### 14.4 In Scope

- 建立最小 AuthLayout。
- 将现有 LoginPage 纳入 AuthLayout。
- 新增 `/forgot-password`。
- 登录页与忘记密码页互相导航。
- 保留当前 `admin/admin` mock 登录行为。
- 真实姓名仅作为组件内存字段。
- 登录成功进入默认业务入口。
- 登录失败只执行本地 mock 校验。
- 退出继续要求确认。
- 刷新后不恢复 auth。
- 忘记密码提交显示明确 mock 提示。

Gate 5 合并后，登录成功流程才增加合法 Tab 恢复能力。

### 14.5 ForgotPassword Content

主标题和未来流程说明可以保留产品文案，但页面必须显著显示：

> 当前为前端模拟流程，不会实际发送飞书卡片。

提交后的反馈必须为：

> 模拟提交成功：当前不会实际发送飞书卡片。

禁止：

- 暗示已经真实发送。
- 区分用户是否存在。
- 保存输入姓名。
- 将姓名写入 URL、日志或错误报告。

### 14.6 Out of Scope

- 注册
- 验证码
- 短信
- 邮件
- SSO
- OAuth
- 真实飞书登录
- 真实飞书卡片
- reset token
- 用户存在性查询
- auth service
- API client
- token store
- permission store
- Tab Restore
- KeepAlive
- PageShell
- ErrorBoundary

### 14.7 Allowed Files

- `frontend/src/App.tsx`
- `frontend/src/App.test.tsx`
- `frontend/src/router/routes.tsx`
- `frontend/src/router/routes.test.tsx`
- `frontend/src/layouts/auth/AuthLayout.tsx`
- `frontend/src/layouts/auth/AuthLayout.css`
- `frontend/src/layouts/auth/AuthLayout.test.tsx`
- `frontend/src/pages/auth/LoginPage.tsx`
- `frontend/src/pages/auth/LoginPage.css`
- `frontend/src/pages/auth/LoginPage.test.tsx`
- `frontend/src/pages/auth/ForgotPasswordPage.tsx`
- `frontend/src/pages/auth/ForgotPasswordPage.css`
- `frontend/src/pages/auth/ForgotPasswordPage.test.tsx`
- 现有 mock auth 文件，仅限维持当前 mock 行为所需的最小修改

### 14.8 Forbidden Files

除全局禁止范围外，本 Gate 禁止修改：

- `frontend/src/config/navigation.ts`
- MainLayout 导航结构
- PageShell 文件
- Error Shell 文件
- Tab workspace 文件
- 真实 API client
- auth/permission store

### 14.9 Tests

至少覆盖：

- `/login` 渲染
- `/forgot-password` 渲染
- 两个页面互相导航
- mock 登录成功
- mock 登录失败
- 退出确认
- 刷新不恢复 auth
- Forgot 空输入校验
- Forgot mock 成功提示
- 明确提示不会真实发送
- 不区分用户是否存在
- 不请求网络
- 姓名不进入 storage
- 姓名不进入 URL
- storage 中不存在 password、token、role、permission、auth boolean 或完整用户对象

### 14.10 Manual Acceptance

至少检查：

- LoginPage 与 ForgotPasswordPage 复用同一个 AuthLayout。
- 品牌区没有复制两套结构。
- 返回按钮回登录页。
- mock 提示清晰可见。
- 成功反馈不暗示真实发送。
- 桌面和窄屏布局正常。
- 登录成功进入默认业务入口。
- 刷新后回登录页。

### 14.11 Rollback Boundary

回滚 Gate 2 后：

- Gate 1 路由基础继续可用。
- LoginPage 恢复为唯一认证入口。
- 不留下 ForgotPassword route 或未使用 AuthLayout。

### 14.12 Definition of Done

- AuthLayout 完成。
- LoginPage 纳入 AuthLayout。
- ForgotPassword mock 页面完成。
- 无真实认证、API 或飞书调用。
- 无敏感数据持久化。
- 测试、lint、build、diff-check 通过。

## 15. Gate 3 — Page Foundation

### 15.1 Branch

`feat/frontend-page-foundation`

### 15.2 Dependency

Gate 2 已合并，负责人已同步最新 `main`，并单独批准 Gate 3。

### 15.3 Goal

建立后续页面共用的最小 PageShell 和唯一 ComingSoonPage。

### 15.4 In Scope

- 新增一个通用 PageShell。
- 新增一个通用 ComingSoonPage。
- 尚未 ready 的页面统一使用 ComingSoonPage。
- title、status、help 等从 `navigation.ts` 解析。
- 页面帮助入口按项目规则在新标签页打开。
- Breadcrumb 继续由 MainLayout 顶部区域统一渲染。
- PageShell 不渲染第二套 Breadcrumb。
- `permissionKey` 保留为 metadata，但不向普通用户展示。
- PageShell 只实现当前已有消费者需要的最小页面壳。

### 15.5 Out of Scope

- 为每个菜单创建独立占位页面
- 复制 navigation metadata
- 显示 permissionKey
- Debug Panel
- dev mode 权限面板
- 权限校验
- 真实页面内容
- LegacyPageWrapper
- 业务模块目录树
- API 请求
- ListPageShell
- FormPageShell
- Dirty Form Guard
- Error Shell
- Tab Restore
- KeepAlive

### 15.6 Allowed Files

- `frontend/src/router/routes.tsx`
- `frontend/src/router/routes.test.tsx`
- `frontend/src/layouts/MainLayout.tsx`
- `frontend/src/layouts/MainLayout.test.tsx`
- `frontend/src/components/page/PageShell.tsx`
- `frontend/src/components/page/PageShell.css`
- `frontend/src/components/page/PageShell.test.tsx`
- `frontend/src/pages/ComingSoonPage.tsx`
- `frontend/src/pages/ComingSoonPage.css`
- `frontend/src/pages/ComingSoonPage.test.tsx`
- `docs/UI_COMPONENT_CATALOG.md`

`docs/UI_COMPONENT_CATALOG.md` 仅在 PageShell 和 ComingSoonPage 实际合并时做最小登记。

### 15.7 Conditional File

`frontend/src/config/navigation.ts` 默认禁止修改。

只有在：

1. 现有 metadata 确实不足；
2. 工程师停止实现并报告；
3. 负责人明确批准；
4. Gate 3 执行 Prompt 和允许文件清单已更新；

四项全部满足后，才能修改。

### 15.8 Forbidden Files

除全局禁止范围外，本 Gate 禁止修改：

- Auth 页面视觉文件
- Error Shell 文件
- Tab workspace 文件
- 业务页面目录
- navigation metadata，除非完成条件授权

### 15.9 Tests

至少覆盖：

- PageShell 显示正确 title。
- PageShell 显示正确 status。
- Help 来源于 navigation metadata。
- Help 使用新标签页语义。
- 普通页面不显示 permissionKey。
- Breadcrumb 内容正确。
- 页面中只存在一套 Breadcrumb。
- 非 ready 页面统一使用 ComingSoonPage。
- 不为每个菜单创建独立页面。
- disabled 页面不可用。
- hidden 页面按 route resolver 规则处理。
- 不执行权限判断。
- 不发送网络请求。

### 15.10 Manual Acceptance

至少检查：

- MainLayout 未被破坏。
- 一级导航和二级 flyout 保持原行为。
- Topbar 保持原行为。
- Breadcrumb 不重复。
- PageShell 不显示 permissionKey。
- ComingSoonPage 信息清晰。
- 帮助入口可用。
- 桌面与窄屏正常。
- 无整页滚动异常。

### 15.11 Rollback Boundary

回滚 Gate 3 后：

- Gate 1/2 的 Router 和 Auth Routes 继续工作。
- 业务 Content 恢复 Gate 1 的临时占位逻辑。
- 不留下未使用的 PageShell 或 ComingSoonPage route。

### 15.12 Definition of Done

- 最小 PageShell 完成。
- 唯一 ComingSoonPage 完成。
- 非 ready 页面统一渲染。
- Breadcrumb 没有重复。
- permissionKey 未面向普通用户显示。
- 未创建大量占位页面。
- 测试、lint、build、diff-check 通过。

## 16. Gate 4 — Error Shell

### 16.1 Branch

`feat/frontend-error-shell`

### 16.2 Dependency

Gate 3 已合并，负责人已同步最新 `main`，并单独批准 Gate 4。

### 16.3 Goal

建立最小前端错误壳。

### 16.4 In Scope

- 静态 404 页面。
- React ErrorBoundary。
- 500 fallback UI。
- 未匹配合法路由的 URL 显示 404。
- 渲染错误显示 500 fallback。
- 提供安全的返回默认入口操作。
- 登录区域与业务区域的错误边界行为明确。
- 开发环境错误不能被静默吞掉。
- 生产 fallback 不显示敏感错误细节。

### 16.5 Out of Scope

- Sentry
- 外部监控平台
- 错误上报 API
- 401 页面
- 403 页面
- 权限判断
- 后端错误码映射
- Error analytics
- 生产测试 route
- 生产测试页面

### 16.6 Allowed Files

- `frontend/src/App.tsx`
- `frontend/src/App.test.tsx`
- `frontend/src/router/routes.tsx`
- `frontend/src/router/routes.test.tsx`
- `frontend/src/components/errors/AppErrorBoundary.tsx`
- `frontend/src/components/errors/AppErrorBoundary.test.tsx`
- `frontend/src/pages/errors/NotFoundPage.tsx`
- `frontend/src/pages/errors/NotFoundPage.test.tsx`
- `frontend/src/pages/errors/ErrorFallbackPage.tsx`
- `frontend/src/pages/errors/ErrorFallbackPage.test.tsx`
- `frontend/src/pages/errors/ErrorPages.css`

只允许一份最小共用错误页样式。

### 16.7 Forbidden Files

除全局禁止范围外，本 Gate 禁止修改：

- navigation metadata
- auth 行为
- Tab workspace
- 业务页面
- 权限配置
- API client
- 监控配置

### 16.8 Tests

至少覆盖：

- unknown path 显示 404。
- 404 返回默认入口。
- 测试组件抛出渲染错误后显示 500 fallback。
- ErrorBoundary 不产生无限重渲染。
- 不发送外部请求。
- 页面不显示 stack。
- 页面不显示 token、用户数据或环境变量。
- 登录页与业务区错误边界行为明确。

抛错 fixture 必须仅存在于测试文件中，不得新增生产测试页面或 route。

### 16.9 Manual Acceptance

至少检查：

- 未知 path 显示 404。
- 404 可返回安全入口。
- 500 fallback 视觉清晰。
- 错误页不泄露技术细节。
- 桌面与窄屏正常。
- 不影响 LoginPage、ForgotPasswordPage、PageShell 和 ComingSoonPage。

### 16.10 Rollback Boundary

回滚 Gate 4 后：

- 恢复 Gate 1 的临时 unknown path 回退。
- Gate 1–3 的正常路由、AuthLayout 和 PageShell 继续工作。
- 不留下生产测试 route。

### 16.11 Definition of Done

- 404 完成。
- ErrorBoundary 完成。
- 500 fallback 完成。
- 不接监控或上报 API。
- 不泄露敏感信息。
- 测试、lint、build、diff-check 通过。

## 17. Gate 5 — Tab Lifecycle

### 17.1 Branch

`feat/frontend-tab-lifecycle`

### 17.2 Dependency

Gate 4 已合并，负责人已同步最新 `main`，并单独批准 Gate 5。

### 17.3 Goal

完成 URL、Tab、sessionStorage 和页面组件生命周期闭环。

### 17.4 In Scope

- URL 是 active page 权威来源。
- Tab workspace 只管理 open paths 和顺序。
- 首页 Tab 固定且不可关闭。
- 最多打开 12 个 Tab。
- 第 13 个 Tab 被拒绝并提示用户关闭旧 Tab。
- 不自动淘汰。
- 当前会话切换 Tab 时保留页面组件状态。
- 关闭 Tab 后卸载对应页面组件。
- 关闭后重新打开时页面状态重置。
- 普通刷新后 auth 丢失并回到登录。
- 普通刷新保留合法 path-only workspace。
- 重新 mock 登录后恢复合法 Tabs。
- 刷新后页面内部状态重置。
- 主动退出清除 Tab workspace。
- storage 损坏、版本不支持或含非法 path 时安全回退。

### 17.5 State Owner

默认状态所有者：

- `frontend/src/layouts/useTabWorkspace.ts`

该 hook/module 负责：

- open paths
- Tab 顺序
- 固定首页
- 最大数量
- 打开/关闭操作
- storage 读写和清除
- 恢复校验

URL 继续由 Router 负责。

如果工程师认为必须使用 Zustand，必须先：

1. 停止实现；
2. 说明现有 hook/module 无法满足的具体原因；
3. 获得负责人批准；
4. 更新 Gate 5 允许文件清单。

不得同时创建 hook 和 Zustand Store。

### 17.6 Out of Scope

- Tab 右键菜单
- 关闭左侧
- 关闭右侧
- 关闭其他
- 关闭全部
- 固定/取消固定
- 右键刷新
- LRU
- 自动淘汰
- 持久化页面内部状态
- 持久化表单草稿
- 持久化业务数据
- 真实权限
- 真实 API
- 第三方 KeepAlive 依赖
- 生产测试页面
- 测试 navigation metadata

### 17.7 Allowed Files

- `frontend/src/App.tsx`
- `frontend/src/App.test.tsx`
- `frontend/src/router/routes.tsx`
- `frontend/src/router/routes.test.tsx`
- `frontend/src/router/routeResolver.ts`
- `frontend/src/router/routeResolver.test.ts`
- `frontend/src/layouts/MainLayout.tsx`
- `frontend/src/layouts/MainLayout.css`
- `frontend/src/layouts/MainLayout.test.tsx`
- `frontend/src/layouts/useTabWorkspace.ts`
- `frontend/src/layouts/useTabWorkspace.test.ts`
- `docs/architecture/frontend.md`

文档只允许同步：

- path-only storage schema
- 普通刷新恢复规则
- 主动退出清理规则
- KeepAlive 生命周期
- 首页固定和 12 Tab 上限

### 17.8 Forbidden Files

除全局禁止范围外，本 Gate 原则上禁止修改：

- `frontend/src/config/navigation.ts`
- Auth 页面视觉文件
- PageShell 视觉文件
- Error Shell 视觉文件
- 业务页面
- 新 Store 文件
- 生产测试 route
- 生产测试页面

### 17.9 KeepAlive Test Fixture

允许测试专用 fixture，但必须：

- 只定义在测试文件中。
- 不新增生产页面。
- 不新增 navigation metadata。
- 不新增正式 route。
- 不创建业务页面。
- 不暴露在真实 UI。
- 不进入生产 bundle 的功能路径。

视觉验收只验证 Tab 切换体验，不要求在生产页面显示测试计数器或状态输入控件。

### 17.10 Tests

至少覆盖：

- 首页 Tab 固定。
- 首页 Tab 不可关闭。
- 打开新 Tab。
- 重复 path 不产生重复 Tab。
- Tab 顺序稳定。
- 点击 Tab 更新 URL。
- 浏览器前进/后退更新 active Tab。
- 关闭非活动 Tab。
- 关闭活动 Tab 后选择确定的相邻 Tab。
- 达到 12 个 Tab。
- 第 13 个 Tab 被拒绝。
- 显示明确提示。
- 不自动淘汰。
- 当前会话切换时 fixture 状态保留。
- 关闭后重新打开时 fixture 状态重置。
- 普通刷新后先进入登录。
- 重新 mock 登录后恢复合法 Tabs。
- 刷新后 fixture 内部状态重置。
- 主动退出清除 storage。
- 主动退出后重新登录只显示默认首页。
- 损坏 JSON 安全回退。
- 不支持的 schema version 安全回退。
- unknown path 被过滤。
- disabled path 被过滤。
- hidden 合法 path 按 resolver 规则恢复。
- activePath 无效时安全回退。
- 默认首页缺失时自动补齐。
- storage 只包含 version、openPaths、activePath。
- storage 不包含完整 navigation item。
- storage 不包含任何认证、权限或页面内部状态。
- 不依赖网络。

### 17.11 Manual Acceptance

至少检查：

- 首页 Tab 固定且无关闭按钮。
- 打开多个 Tab 后顺序稳定。
- 点击 Tab 与 URL 同步。
- 浏览器前进/后退同步 active Tab。
- 第 13 个 Tab 触发提示。
- 不会自动关闭旧 Tab。
- 关闭活动 Tab 后选择规则稳定。
- 当前会话切换体验保留。
- 普通刷新后回登录。
- 重新登录后恢复合法 Tabs。
- 主动退出后不恢复旧 Tabs。
- 无整页滚动异常。

### 17.12 Rollback Boundary

回滚 Gate 5 后：

- Router、Auth Routes、PageShell 和 Error Shell 保持可用。
- Tabbar 恢复 Gate 4 的内存行为。
- 不留下 storage key。
- 不留下未使用的 workspace hook。
- 不留下 KeepAlive 容器。
- 不影响 navigation metadata。

### 17.13 Definition of Done

- 唯一 Tab workspace owner 建立。
- path-only restore 完成。
- 主动退出清理完成。
- 最小 KeepAlive 生命周期完成。
- 首页固定完成。
- 12 Tab 上限完成。
- 非法 storage 安全回退。
- 测试、lint、build、diff-check 通过。
- 未新增依赖或生产测试页面。

## 18. Shared Test Requirements

每个 Gate 完成后至少执行：

```
git branch --show-current
git status --short
git diff --stat
git diff
git diff --check
cd frontend
npm run lint
npm run test -- --run
npm run build
```

不得运行：

```
npm install
npm update
npm audit fix
```

每个 Gate 完成报告必须记录：

- 当前分支
- Node 版本
- 修改文件
- untracked 文件
- 测试文件数量
- 测试数量
- lint 结果
- build 结果
- diff-check 结果
- 既有大 chunk 警告
- 是否调用外部 API
- 是否写 storage
- storage 具体 schema
- 是否修改 navigation metadata
- 是否存在 `.planning/**` 未跟踪文件
- 是否使用外部 Agent/Skill

不得通过以下方式让测试表面通过：

- `.only`
- `.skip`
- 删除关键断言
- 全局提高 timeout
- 无理由提高单测 timeout
- 依赖真实网络
- 创建生产测试页面

## 19. Manual UI Acceptance Matrix

### Gate 1

- `/login`
- 默认业务入口
- 菜单点击
- Tab 点击
- 浏览器前进/后退
- hash 刷新
- 退出
- 无异常滚动

### Gate 2

- `/login`
- `/forgot-password`
- AuthLayout
- mock 登录成功/失败
- Forgot mock 提示
- 返回登录
- 刷新后回登录
- 桌面与窄屏

### Gate 3

- PageShell
- ComingSoonPage
- Help
- 单一 Breadcrumb
- permissionKey 不显示
- MainLayout 回归
- 桌面与窄屏
- 无异常滚动

### Gate 4

- 404
- 返回入口
- 500 fallback
- 不泄露敏感信息
- 桌面与窄屏

### Gate 5

- 首页固定
- 多 Tab 顺序
- 切换与关闭
- 12 Tab 上限
- 前进/后退
- 普通刷新恢复
- 主动退出清空
- 无异常滚动

## 20. Security Checklist

所有 Gate 必须确认：

- 不调用真实 API。
- 不连接后端。
- 不连接数据库。
- 不读取或运行 old-system。
- 不保存 password。
- 不保存 token。
- 不保存 role。
- 不保存 permission。
- 不保存 auth boolean。
- 不保存完整用户对象。
- 不持久化飞书真实姓名。
- 不把姓名写入 URL 或日志。
- 不提交密钥或 `.env*`。
- 不实现前端权限伪安全。
- 不在错误页泄露 stack、用户数据或环境变量。
- 不把测试 fixture 暴露到生产 UI。
- 不修改 Vercel 或 CI。
- 主动退出清除 Tab workspace。
- sessionStorage 只保存 path-only schema。

Gate 2 和 Gate 5 必须重点进行安全审查。

## 21. Documentation Synchronization

文档修改必须最小化，并复用现有权威文件。

### Gate 1

可修改：

- `docs/01_PROJECT_DECISIONS.md`
- `docs/architecture/frontend.md`
- `docs/AI_GIT_DEV_RULES.md`

仅记录：

- HashRouter
- URL 权威状态源
- route resolver
- `main` 集成基线
- Routing-first 受控例外

### Gate 3

可修改：

- `docs/UI_COMPONENT_CATALOG.md`

仅登记实际合并的：

- PageShell
- ComingSoonPage

### Gate 5

可修改：

- `docs/architecture/frontend.md`

仅记录：

- path-only storage schema
- 普通刷新恢复
- 主动退出清理
- KeepAlive 生命周期
- 首页固定
- 12 Tab 上限

### Documentation Restrictions

禁止：

- 新建重复 Routing Rules
- 新建重复 Tab Rules
- 新建重复 PageShell Rules
- 修改 `AGENTS.md` 弱化任务粒度
- 大范围重写 FIRST\_40
- 修改无关文档
- 让文档描述超前于实际合并功能

Rule Pack Maintainer 必须检查规则单一来源。如同步需要超出 Gate Allowed Files，必须先请求负责人授权。

## 22. Agents and Skills Responsibilities

Agents/Skills 只能在职责范围内提供建议、检查和审查：

- 不能覆盖项目规则。
- 不能扩大 Gate 范围。
- 不能自行授权开发。
- 不能替负责人执行提交、上传或合并。

| Agent / Skill职责使用阶段       |                                           |              |
| ------------------------- | ----------------------------------------- | ------------ |
| Project Shepherd          | 控制五个 Gate、依赖顺序和交付边界                       | 总体规划         |
| Feature Slice Planner     | 保证一个 Gate 一个清晰功能切片                        | 总体规划、Gate 拆分 |
| Technical Writer          | PRP、架构决策和规则同步表达                           | PRP、文档       |
| Rule Pack Maintainer      | 检查规则冲突和单一规则来源                             | 文档同步         |
| Ponytail                  | 最小实现、依赖守卫、避免过度扩展                          | 每个 Gate      |
| Minimal Change Engineer   | 控制最小必要改动                                  | 每个 Gate      |
| Frontend Developer        | React、Router 和 UI 实现建议                    | 每个 Gate      |
| React Component Architect | AuthLayout、PageShell、Error Shell 和 Tab 边界 | Gate 2–5     |
| Evidence Collector        | 收集测试、视觉和行为证据                              | 每个 Gate      |
| Page Acceptance Checker   | 新页面及页面壳验收                                 | Gate 2–4     |
| Code Reviewer             | 正确性、边界和回归审查                               | 每个 Gate      |
| Code Review Checker       | diff、untracked 和禁止文件检查                    | 每个 Gate      |
| Git Workflow Master       | 分支、worktree 和负责人上传边界                      | 每个 Gate      |
| Context7/官方文档             | 核对 React Router 当前版本 API                  | Gate 1       |

### Gate 1 Documentation Lookup

Gate 1 必须按 `frontend/package.json` 的实际 React Router 版本核对：

- HashRouter
- Routes
- Route
- Navigate
- useLocation
- useNavigate
- 浏览器前进/后退
- 测试环境 Router 用法

完成报告必须说明：

- 查询版本
- 查询问题
- 结论
- 不确定点

Context7 或外部工具不得成为生产依赖，也不得写入密钥。

### Agents Not Participating

本轮默认不需要：

- Backend Architect
- API Tester
- Database Optimizer
- Database Reliability Engineer
- DevOps Automator
- Multi-Agent Systems Architect

如果范围变化为 API、后端、数据库、部署或生产配置，必须重新进行 agent routing 和 PRP 评估。

## 23. Branch and PR Strategy

五个 Gate 分支：

1. `feat/frontend-routing-foundation`
2. `feat/frontend-auth-routes`
3. `feat/frontend-page-foundation`
4. `feat/frontend-error-shell`
5. `feat/frontend-tab-lifecycle`

规则：

- 每个 Gate 从当时最新 `main` 创建。
- 一个 Gate 一个分支、一个 PR。
- 不从未合并的功能分支继续开发。
- 不创建超级 PR。
- 不跨 Gate 实现。
- commit 数量和 squash 策略由负责人决定。
- 工程师只提供建议 commit message。
- Gate 1 PR 默认纳入已批准的总 PRP。
- 总 PRP Approved 后，每个 Gate仍需单独负责人确认。

工程师禁止：

- `git add`
- `git commit`
- `git push`
- force push
- `gh pr create`
- 创建 PR
- 合并 PR
- 删除远程分支
- 修改 `main`

负责人本人负责上传和合并。

## 24. `.planning/**` Rule

`.planning/**` 只能作为本地计划资料。

明确禁止：

- 进入 Suggested staging list
- `git add`
- commit
- push
- 进入 PR

工程师完成报告必须：

- 运行 `git status --short`
- 报告是否存在 `.planning/**` 未跟踪文件
- 明确将其排除在建议暂存文件之外

`.planning/**` 的存在不等于产品文件改动，但不得上传。

## 25. Rollback Strategy

总体原则：

- 每个 Gate 必须可独立 revert。
- 后一个 Gate 可以依赖前一个 Gate，但不能让前一个 Gate失去独立运行能力。
- 任一 Gate 失败时，不得牵连未开始的 Gate。
- 不把多个失败域压入同一个 PR。

回滚边界：

1. Gate 1：恢复现有内存导航。
2. Gate 2：保留 Gate 1 Router，移除 AuthLayout/Forgot。
3. Gate 3：保留 Router/Auth，恢复临时 Content 占位。
4. Gate 4：恢复 Gate 1 unknown path 临时回退。
5. Gate 5：保留前四个 Gate，恢复内存 Tab 行为并清理 storage。

## 26. Risks and Mitigations

### 26.1 状态源重复

风险：

- Router、MainLayout 和 Tab workspace 同时维护 active page。

控制：

- URL 是 active page 权威来源。
- Tab workspace 只维护 open paths。
- 只允许一个 Tab workspace owner。

### 26.2 Route Eligibility 分叉

风险：

- Router、Breadcrumb、Tab Restore 分别判断 hidden/disabled。

控制：

- 统一 route resolver。
- 所有消费者复用 resolver。
- 不复制过滤条件。

### 26.3 Navigation Metadata 被完整持久化

风险：

- storage 中保存完整 navigation item，包含 permissionKey 等字段。

控制：

- path-only schema。
- 恢复时重新解析 metadata。
- 测试实际序列化结果。

### 26.4 Mock Auth 被持久化

风险：

- 为恢复 Tabs 顺带保存 auth。

控制：

- auth 只在内存。
- 普通刷新先回登录。
- 主动退出清除 workspace。
- 测试 storage 白名单。

### 26.5 KeepAlive 过度工程化

风险：

- 引入缓存库、复杂 Store 或通用框架。

控制：

- 不新增依赖。
- 默认最小 hook/module。
- 只满足 Tab 切换、关闭和刷新语义。

### 26.6 PageShell 过度扩展

风险：

- 提前实现列表、表单、权限或 Debug 框架。

控制：

- PageShell 只服务当前消费者。
- 不显示 permissionKey。
- List/Form Shell 延期。

### 26.7 ForgotPassword 误导用户

风险：

- 页面让用户误以为已经真实发送卡片。

控制：

- 页面显著标注 mock。
- 成功提示明确不会发送。
- 不保存姓名。
- 不区分用户是否存在。

### 26.8 错误页泄露信息

风险：

- fallback 输出 stack、环境变量或用户数据。

控制：

- 生产 UI 使用通用文案。
- fixture 只在测试中。
- 不接外部监控或上报。

### 26.9 Git 文档仍使用 `dev`

风险：

- 新分支基线与实际流程冲突。

控制：

- Gate 1 只做最小规则同步。
- 不新建第二份 Git 规则。
- 不大范围改写无关内容。

## 27. Deferred Work

以下全部延期：

- LegacyPageWrapper
- 真实认证和 API
- 真实飞书密码重置
- 真实权限
- 401/403 权限页
- 后端错误映射
- ListPageShell
- FormPageShell
- Dirty Form Guard
- Tab 右键菜单
- Tab 批量关闭
- LRU 淘汰
- 页面业务状态持久化
- 全局搜索
- 最近访问
- 收藏
- 主题
- 浏览器标题同步
- 前端版本展示
- 开发环境 Banner
- E2E
- Vercel rewrite
- old-system 桥接

## 28. Suggested Commit and PR Naming

以下仅供负责人参考，工程师不得执行提交。

### Gate 1

- Commit：`feat(frontend): add routing foundation`
- PR：`feat(frontend): add routing foundation`

### Gate 2

- Commit：`feat(frontend): add auth routes`
- PR：`feat(frontend): add auth routes`

### Gate 3

- Commit：`feat(frontend): add page foundation`
- PR：`feat(frontend): add page foundation`

### Gate 4

- Commit：`feat(frontend): add error shell`
- PR：`feat(frontend): add error shell`

### Gate 5

- Commit：`feat(frontend): add tab lifecycle`
- PR：`feat(frontend): add tab lifecycle`

## 29. Engineer Completion Report

每个 Gate 完成后必须输出：

```
## Done
## Files changed
## Commands run
## Tests run
## Context / docs checked
## Risk check
- 是否修改 old-system
- 是否连接数据库
- 是否修改 .env
- 是否调用外部 API
- 是否影响权限
- 是否影响数据库迁移
- 是否使用外部 Agent / Skill
- 是否写入 sessionStorage
- sessionStorage 的具体字段
- 是否存在 .planning/** 未跟踪文件
## Acceptance checklist
## git status --short
## git diff --stat
## Suggested staging list
## Suggested commit message
## Suggested PR title and description
## Next step
```

Suggested staging list 必须排除：

- `.planning/**`
- `frontend/dist/**`
- 所有禁止文件
- 与当前 Gate 无关的文件

## 30. Owner Approval Record

负责人已批准并确认：

- 状态为 `Approved`
- 一个总 PRP、五个执行 Gate
- 禁止超级 PR
- 每个 Gate 独立分支、PR、测试、审查、回滚
- `main` 为当前集成基线
- Routing-first 受控调整已记录
- LegacyPageWrapper 已延期
- route resolver 是统一合法路由入口
- URL 是 active page 权威来源
- sessionStorage 使用 path-only schema
- 普通刷新可保留 workspace
- 主动退出清除 workspace
- ForgotPassword 明确为 mock
- PageShell 不显示 permissionKey
- `.planning/**` 不进入 staging、commit 或 PR
- Agents/Skills 职责和边界已记录
- 不接真实 API、认证、权限、后端、数据库或 old-system
- 不修改 Vercel 或 CI
- 工程师禁止提交和上传
- Gate 1 PR 默认纳入已批准的总 PRP
- 总 PRP Approved 不等于连续实施五个 Gate
- 每个 Gate 仍需负责人单独确认和执行 Prompt

批准生效后：

1. 可以单独下发 Gate 1 执行 Prompt。
2. Gate 1 合并并同步最新 `main` 前，不启动 Gate 2。
3. Gate 2–5 后续仍需负责人逐 Gate 单独确认。

> 本 PRP 已批准为总 PRP，但不构成 Gate 2–5 的实现授权。五个 Gate 必须由负责人逐 Gate 批准，并在前一个 Gate 合并且同步最新 `main` 后开始。

## Changes Incorporated

已合并全部确认修订：

- 增加 PRP 批准、逐 Gate 授权和入库流程
- 增加 `.planning/**` 禁止上传规则
- 增加统一 route resolver
- 明确 Gate 1 临时 Content 策略
- sessionStorage 收紧为 path-only schema
- 主动退出清除 Tab workspace
- 普通刷新后重新登录恢复合法 Tabs
- ForgotPassword 明确标注 mock
- PageShell 不显示 permissionKey
- 统一各 Gate 文档允许范围
- 修正一个 Gate 一个分支、一个 PR 的表述
- 补全 Agents/Skills 职责矩阵
- 修复 Markdown code fence 结构
- 明确 Gate 1 PR 默认纳入已批准总 PRP

## Remaining Risks

- Gate 1 开始前，需要根据实际 `navigation.ts` 字段确认 ready/enabled/hidden/disabled 的具体映射；如 metadata 不足，必须停止并报告。
- Gate 5 是复杂度最高的 Gate，必须坚持一个 Tab workspace owner，不得同时增加 hook 和 Store。
- Git 文档若仍以 `dev` 为默认基线，只允许做与当前 `main` 流程直接相关的最小修正。
- KeepAlive 只应满足已确认生命周期，不应演变成通用页面缓存框架。

## Owner Approval Status

- 本总 PRP 已批准。
- 状态已为 `Approved`。
- Gate 1 可以单独启动。
- Gate 1 分支从最新 `main` 创建。
- 已批准 PRP 随 Gate 1 PR 入库。
- 尚未授权 Gate 2–5 实现。
- 后续每个 Gate 仍需单独负责人确认和执行 Prompt。

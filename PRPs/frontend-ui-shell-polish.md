# Frontend UI/Auth Shell Polish PRP

> 状态：Approved — 项目负责人已明确批准本 PRP 及后续确认的受控视觉修正。
>
> 任务：Phase 1 / Combined UI Shell Polish

## 1. Goal

在一次负责人明确授权的综合前端任务中，完善现有 MainLayout UI 壳，并增加纯前端 mock 登录闭环：

- 优化 Tabbar 选中态和 Content 卡片间距。
- 增加顶部通知、AI 助手、用户菜单和退出确认交互。
- 让 AI 助手、个人中心、文档复用 navigation metadata 进入现有 Tab / Breadcrumb / Content 状态。
- 增加“掌上便捷”LoginPage，并以公开测试数据 `admin/admin` 完成内存态 mock 登录与退出闭环。
- 保持现有侧栏、二级 flyout、backdrop、Tab、Breadcrumb 和 Content 的基本行为。

本任务交付的是 UI/Auth Shell，不是正式页面系统、真实鉴权或安全边界。所有新增页面状态均不得标记为 `ready`。

## 2. Why

当前前端已有可用的 MainLayout 结构壳，但缺少统一顶部操作区、实用页面入口和登录前置体验。本任务用受控 mock 数据建立可审查的完整界面演示链路，为后续正式路由、PageShell、认证、权限和业务页面的独立任务提供视觉与交互基线。

## 3. Scope

### In scope

- [ ] MainLayout Tabbar active / inactive / hover / close hover 视觉优化。
- [ ] Main workspace 浅灰背景与白色 Content 卡片四周间距、圆角及视口内布局优化。
- [ ] Header 右侧新增统一 `TopbarActions`：通知铃铛、AI 助手入口、用户头像。
- [ ] 本地 mock 通知面板、绿色未读点、清空和“查看所有消息”占位提示。
- [ ] 通知面板、用户菜单和二级 flyout/backdrop 的互斥与关闭协调。
- [ ] AI 助手复用既有 `ai_center_assistant` navigation metadata。
- [ ] navigation 的 `settings` group 末尾追加 hidden 个人中心页面。
- [ ] navigation 的 `data_center` group 末尾追加 hidden 文档页面。
- [ ] MainLayout 增加按 page key 查找并打开页面的统一最小行为。
- [ ] 用户头像 hover 外圈、用户菜单和本地展示用户信息。
- [ ] 使用负责人提供并批准的唯一默认头像文件 `frontend/public/default-avatar.png`。
- [ ] 退出确认 Modal；确认后仅通过 callback 通知 App。
- [ ] “掌上便捷”响应式 LoginPage 与 `admin/admin` 前端 mock 校验。
- [ ] App 使用 React 内存 state 在 LoginPage 和 MainLayout 间切换。
- [ ] 记住账号时只持久化 username 到 `mock_login_remembered_username`。
- [ ] Vitest、lint、build、diff check 和桌面/窄屏人工视觉验收。

### Out of scope

- [ ] 正式 React Router routes、URL push/replace 或 route guard。
- [ ] PageShell、ComingSoonPage、正式业务页面和页面 `ready` 状态。
- [ ] AuthContext、Zustand auth store、auth service、认证 middleware。
- [ ] 真实登录、退出、Token、Cookie、Session、JWT 或 Authorization header。
- [ ] 角色、权限、permissionKey 校验、菜单过滤或数据权限。
- [ ] 真实通知中心、通知 API、WebSocket 或持久化通知。
- [ ] 真实 AI 能力、聊天输入或 AI API。
- [ ] backend、数据库、迁移、old-system、Vercel 或部署配置。
- [ ] fetch、Axios、外部图片 URL、base64 图片或未经负责人明确批准的新增图片资源；唯一例外为 `frontend/public/default-avatar.png`。
- [ ] 新增/升级依赖、修改 package.json/package-lock/vite.config。
- [ ] Playwright E2E；本阶段仅做 Vitest 和人工浏览器验收。
- [ ] 拖拽 Tab、Tab 右键菜单、Tab 持久化。

## 4. Navigation / Page

```text
默认一级导航：工作台（dashboard）
默认二级页面：今日销售（dashboard_today_sales）
默认页面路径元数据：/dashboard/today-sales
默认页面状态：保留现有状态，不改为 ready

AI 助手：
  group：ai_center
  key：ai_center_assistant
  title/path/status：全部复用现有 navigation metadata

个人中心：
  group：settings
  key：settings_personal_center
  title：个人中心
  path：/settings/personal-center
  status：hidden

文档：
  group：data_center
  key：data_center_documentation
  title：文档
  path：/data-center/documentation
  status：hidden
```

- 两个 hidden 页面使用既有 `page()` helper，分别追加在对应 group 的 children 末尾。
- 不改变任何既有 group/page 的顺序、标题、路径、permissionKey、status、help、tabs、icon 或 children。
- hidden 页面不进入侧栏二级菜单，但必须能被现有 navigation 查找逻辑解析。
- Tab、Breadcrumb、Content 及用户菜单中的页面标题只从 navigation metadata 派生。
- 不创建 `utilityPages`、`topbarPages` 或第二套页面/标题/路由/权限配置。
- 本任务只读取 path 元数据，不注册路由、不修改浏览器 URL。

## 5. Permissions

```text
page permissionKey：沿用 page() helper 生成或既有 navigation metadata；本任务不校验
action permissionKeys：无
data scope resource：无
field permissions：无
high-risk actions：无
```

- `admin/admin` 不对应角色或权限。
- 不写 `role === "admin"`、`isAdmin` 或任何基于 username 的授权判断。
- navigation permissionKey 只是元数据，不代表用户已通过权限校验。
- 本任务 UI 不构成安全边界。

## 6. Data Source / Mock Boundary

```text
old-system reference：no
legacy MySQL readonly tables：none
new PostgreSQL tables：none
cache / mart tables：none
external APIs：none
```

### Mock auth

- `frontend/src/mocks/auth.ts` 只保存明确标注为公开前端测试数据的 mock username/password：`admin/admin`，以及最小校验函数或常量。
- `admin/admin` 不是 Secret、不是生产凭据、不得用于正式认证。
- password 只存在于当前表单运行时，不进入 localStorage/sessionStorage。
- App 的登录状态只存在于 React 内存 state，刷新后重新登录是预期行为。
- 勾选“记住账号”只保存 username 到 `mock_login_remembered_username`；未勾选时删除旧 username。
- 不保存 auth boolean、完整用户、role、permissions、Token、Cookie 或 Session。

### Mock current user

- `frontend/src/mocks/currentUser.ts` 只包含明显虚构的展示数据：`演示用户`、`admin@example.local`、`online: true` 等。
- 不包含真实姓名、手机号、真实邮箱、真实角色、权限或业务数据。

### Mock notifications

- `frontend/src/mocks/notifications.ts` 只包含少量明显虚构的标题、描述、时间、未读状态和本地图标 key。
- 不包含真实订单、店铺、SKU、客户、员工或生产数据。
- 组件只从 mock 模块初始化本地 state，不调用 API、不持久化。

## 7. API Contract

```text
method：none
path：none
request schema：none
response schema：none
error codes：none
meta.source：frontend mock
meta.source_tables：none
request_id：none
```

本任务禁止 fetch、Axios、WebSocket、真实通知/AI/认证请求和 backend 改动。

## 8. UI Requirements

### 8.1 App

- 默认未登录并显示 LoginPage；不得自动登录。
- 登录成功后使用 React 内存 state 渲染 MainLayout，默认进入工作台 / 今日销售。
- 退出确认成功后清除内存登录态并返回 LoginPage。
- 退出不清除用户主动记住的 username。
- 不负责路由、Token、Cookie、权限或网络请求。

### 8.2 LoginPage

- 宽屏左右分栏：左侧浅蓝渐变，右侧白底 Ant Design 表单。
- 左上角复用 `/favicon.ico` 和“掌上便捷”。
- 左侧中部只用 LoginPage 内部 SVG/CSS 几何插画，不新增图片文件。
- 标题“欢迎回来 👋”；副标题“请输入您的账户信息以开始管理您的项目”。
- 账号、`Input.Password`、记住账号、忘记密码和全宽蓝色登录按钮。
- 清晰显示：“演示登录，仅用于前端界面验证，不提供真实身份认证。”
- 错误凭据统一提示“账号或密码错误”。
- 忘记密码只提示“Mock 环境暂不提供密码找回”。
- 窄屏收敛为无横向滚动的单栏。

### 8.3 MainLayout / unified page opening

- 保留当前导航、Tab、Breadcrumb、Content、flyout、backdrop 和品牌返回默认页行为。
- 顶部为完整横向 topbar：左侧品牌区显示 logo + “掌上便捷”，右侧显示 Breadcrumb / 当前页面信息 + 通知 + AI 助手 + 头像。
- 折叠按钮不在 topbar，固定在一级导航栏底部左侧，并继续控制一级导航展开/折叠。
- 品牌 logo 使用 40×40 或不影响 48px topbar 的视觉合理尺寸，不拉伸变形。
- `.main-layout__brand` 的 `border-block-end: 1px solid #f0f0f0;` 是负责人手动增加并确认保留的视觉分隔线，不作为待删除边线。
- 增加最小 `openPageByKey(pageKey)`：从 navigation 查找 group/page，更新 active group/page，复用 Tab 去重新增/切换，并关闭二级 flyout/backdrop。
- TopbarActions 只发送 page key；不得直接管理 Tab/Breadcrumb 或维护页面对象副本。
- 点击 AI 助手、个人中心、文档后，Tab、Breadcrumb、Content 同步到 navigation metadata。
- 无 children 时显示 `${activePage.title}内容区`；存在 children 时保留原兼容能力。
- 不修改 URL、不执行正式路由。

### 8.4 Tabbar / Content

- active Tab 使用浅蓝背景、接近 `#1677ff` 的文字和 10–14px 圆角。
- Tab 左侧 group icon、页面 title、关闭按钮均从现有 Tabs/navigation 能力派生。
- inactive/hover/close-hover 轻量反馈，纯视觉状态使用 CSS。
- Header 维持 48px，Tabbar 紧凑，不撑高顶部。
- workspace 保持浅灰；Content 为白色独立卡片，四周统一间距、10–12px 圆角。
- 继续使用 flex、`min-height: 0`、`min-width: 0`、`overflow: hidden`，不写固定视口减法，不产生 window/body 整页滚动。

### 8.5 TopbarActions

- topbar 品牌区右侧为可收缩 Breadcrumb / 当前页面信息，末端为通知、AI 助手、用户头像；折叠按钮位于一级导航栏底部，不在 topbar。
- 三类点击区域高度、间距一致，hover 有轻反馈，不挤压 Breadcrumb。
- 只新增一个生产组件 `TopbarActions`，不拆 NotificationPanel/UserMenu/hook/store。
- 通过 callbacks 请求打开 page key 和发出已确认退出请求。

### 8.6 Notifications

- Ant Design Button、Badge、Popover、List、Typography、Empty 等现有能力优先。
- 点击铃铛打开/再次点击关闭/点击外部关闭；禁止 hover 自动打开。
- 有未读显示绿色点，无未读或清空后不显示；不用默认蓝点。
- 白底、圆角、轻阴影、分割线；每项显示标题、描述、时间和未读状态。
- “清空”只清本地 state；空列表显示轻量空状态。
- “查看所有消息”只提示“通知中心将在后续接入”，不新增页面或 Tab。
- 不持久化、不调用 API、不使用 `dangerouslySetInnerHTML`。

### 8.7 AI / user menu / logout

- AI 助手是 page-key 入口，不是 Dropdown、Popover 或 Modal。
- 头像圆形，hover 外圈不改变元素尺寸、不引起 Header 抖动。
- Header 小头像和用户菜单大头像均使用 `/default-avatar.png`，加载失败时显示子文本“掌”。
- 用户菜单以 hover 为主要触发方式，同时支持键盘 focus 打开，并在 blur、焦点移出或点击外部时关闭。
- 用户菜单显示 mock 头像、演示用户、`admin@example.local` 和绿色在线状态；不显示 Admin/Pro/会员等级。
- 个人中心和文档标题从 navigation metadata 派生；另有退出操作。
- 通知与用户菜单互斥；打开顶部目标页时关闭通知、用户菜单、flyout/backdrop。
- 退出菜单先关闭，再打开 Ant Design Modal：标题“提示”、内容“是否退出登录？”、取消/确认及关闭 X。
- 取消/X 不退出；确认只调用一次 `onLogout`；不调用真实 logout API。

### Accessibility

- 图标按钮提供明确 aria-label；表单 label、错误提示、Modal 和菜单均可由语义角色定位。
- 保留品牌 button 和键盘访问能力。
- 用户头像按钮支持键盘 focus 打开用户菜单；焦点可进入菜单，离开头像和菜单范围后关闭。
- Popover/Modal 关闭、互斥和焦点行为优先使用 Ant Design 5.29.3 的现有 API。
- 动画保持克制，并尊重现有 `prefers-reduced-motion` 规则。

## 9. SOP / API Docs

- [ ] Markdown API doc：不适用，本任务无 API。
- [ ] OpenAPI metadata：不适用。
- [ ] SOP help page：本任务不新增正式页面，不创建 SOP。
- [ ] PageShell help entry：不适用，本任务明确不实现 PageShell。
- [ ] Playwright E2E：本阶段不要求；页面不得因此标记为 ready。

## 10. Implementation Plan

> 以下步骤仅在负责人明确批准本 PRP 后执行。

1. 创建 `.planning/current/task_plan.md`、`findings.md`、`progress.md`，记录范围、检查和测试；不纳入建议暂存。
2. 完整读取任务指定项目规则、前端规则和 `skills/react-component-architect/SKILL.md`。
3. 核对 Ant Design 5.29.3 的 Popover、Badge、Modal、Form、Input.Password、Tabs、List/Empty API；有疑问优先 Context7，否则查对应版本官方文档并记录结论。
4. 仅在 navigation 对应 group 末尾追加个人中心和文档 hidden 页面，并补 hidden 不出侧栏/仍可查找测试。
5. 创建集中 mock 数据模块；实现 LoginPage 和测试。
6. 创建 TopbarActions 和测试，使用 Ant Design 管理浮层、互斥、通知和退出确认。
7. 最小修改 App 和 MainLayout，统一 page-key 打开行为、mock 登录切换和顶部 actions 协调。
8. 仅在允许 CSS 文件中完成 Tabbar、Content、顶部区、LoginPage 响应式视觉。
9. 运行 lint、Vitest、build、diff check；按允许范围修复真实失败。
10. 本地人工检查宽屏/窄屏、所有浮层互斥、退出路径和无整页滚动，随后停止服务。
11. 输出范围、验证、风险、原始 Git 状态和建议上传信息；不执行上传。

### Minimal production component split

```text
TopbarActions：通知、AI 入口、用户菜单、退出确认及互斥
LoginPage：表单视觉、mock 校验、记住 username 和登录 callback
App：内存登录态及 LoginPage/MainLayout 切换
MainLayout：navigation/Tab/Breadcrumb/Content 状态和统一 page-key 打开
```

不继续拆 NotificationPanel、UserMenu、hook、store、auth service 或配置副本。

## 11. Test Plan and Validation Gates

### MainLayout.test.tsx

- 直接渲染 `<MainLayout />`，不依赖 App 登录入口。
- 保留默认工作台/今日销售、一级/二级导航、flyout/backdrop、hover、Tab、品牌、折叠和 URL 不变测试。
- 增加 AI 助手、个人中心、文档的 Tab/Breadcrumb/Content 同步测试。
- 确认 hidden 页面不出现在侧栏、顶部入口关闭 flyout/backdrop、重复打开不创建重复 Tab。

### TopbarActions.test.tsx

- 覆盖绿色未读点、铃铛点击开关、外部关闭、清空和空状态、查看全部本地提示。
- 覆盖通知与用户菜单互斥，以及 AI/个人中心/文档 page key callbacks。
- 覆盖用户菜单 hover 与键盘 focus/blur、外部关闭、头像加载失败文本 fallback、退出 Modal、取消/X 不退出、确认只调用一次。
- 覆盖基础 aria label。

### LoginPage.test.tsx

- 覆盖品牌、免责声明、主动提交、`admin/admin` 成功和统一失败信息。
- 覆盖只记 username、未勾选删除旧 username、password 不进入任何 storage。
- 覆盖忘记密码仅显示本地提示。

### App.test.tsx

- 覆盖初始 LoginPage、成功进入 MainLayout、默认今日销售。
- 覆盖退出 Modal 的取消/X/确认路径及确认后返回 LoginPage。
- 覆盖退出保留主动记住的 username，且全过程没有网络请求。

### Isolation

- 所有 storage 测试前后清理 localStorage/sessionStorage。
- 不修改 vite.config、不新增依赖、不增加 E2E。

### Commands

使用 Node.js 24 LTS，禁止运行 `npm install`：

```bash
cd frontend
npm run lint
npm run test -- --run
npm run build
cd ..
git diff --check
git status --short
git diff --stat
git diff
```

### Manual visual validation

- 宽屏登录页左右分栏；窄屏单栏、无横向滚动。
- logo、免责声明、密码显示/隐藏和错误提示。
- MainLayout 默认/展开/折叠、active/inactive Tab、close hover、Content 四周间距、无 body/window 滚动。
- 通知绿点、通知面板、清空空状态和查看全部提示。
- AI 助手、个人中心、文档的 Tab/Breadcrumb/Content。
- 头像 hover 圈、用户菜单、退出 Modal 的取消/X/确认。
- 通知、用户菜单和二级 flyout 不同时打开。
- 截图仅用于交接，不写入仓库；检查后停止 dev server。

## 12. Allowed Files

实现代码和测试仅允许：

```text
frontend/src/App.tsx
frontend/src/App.test.tsx
frontend/src/config/navigation.ts
frontend/src/layouts/MainLayout.tsx
frontend/src/layouts/MainLayout.css
frontend/src/layouts/MainLayout.test.tsx
frontend/src/layouts/components/TopbarActions.tsx
frontend/src/layouts/components/TopbarActions.css
frontend/src/layouts/components/TopbarActions.test.tsx
frontend/src/pages/auth/LoginPage.tsx
frontend/src/pages/auth/LoginPage.css
frontend/src/pages/auth/LoginPage.test.tsx
frontend/src/mocks/auth.ts
frontend/src/mocks/currentUser.ts
frontend/src/mocks/notifications.ts
frontend/public/default-avatar.png
```

规划文件仅允许：

```text
PRPs/frontend-ui-shell-polish.md
.planning/current/task_plan.md
.planning/current/findings.md
.planning/current/progress.md
```

只创建实际使用的文件；`.planning/current/**` 不纳入建议暂存。

## 13. Forbidden Actions

- 不修改 `old-system/**`、`backend/**`、`docs/**`、`.github/**`、`.env*`。
- 不修改 Vercel、frontend public（负责人明确批准的唯一文件 `frontend/public/default-avatar.png` 除外）、assets/router/components/stores/dist、index.html、package.json、package-lock 或 vite.config。
- 不新增/升级依赖，不运行 `npm install`。
- 不接数据库、API、真实用户/通知/AI 数据，不读取 old-system。
- 不实现正式 routes、PageShell、ComingSoonPage、权限、业务页面或 E2E。
- 不保存 password/token/role/permission/auth state，不写真实 Secret。
- 不创建第二套导航/页面标题/路由/权限配置。
- 不大范围格式化或顺手重构。
- 不执行 `git add`、`git commit`、`git push`、`gh pr create`、merge 或删除远程分支。
- 如必须超出允许范围，立即停止并请求负责人拆任务或明确授权。

## 14. Rollback Plan

- 本任务为一次性综合前端 PR，回滚方式为整体 revert 该 PR。
- 无数据库、迁移、后端、环境变量、Vercel、外部 API 或持久化认证状态需要回滚。
- 记住账号仅使用 `mock_login_remembered_username`；如回滚后浏览器仍有该值，可由用户清理 localStorage，不涉及密码或认证状态。
- 不拆分部分回滚，以避免 App/LoginPage/MainLayout/TopbarActions 状态契约不一致。

## 15. Acceptance Checklist

- [ ] PRP 已由负责人明确批准，且实现前已创建本地计划文件。
- [ ] 仅修改允许文件，没有携带其他任务 diff。
- [ ] 默认未登录；必须主动用公开 mock `admin/admin` 提交后进入 MainLayout。
- [ ] 登录态仅在 React 内存；只允许记住 username；password/token/role/permission 均未持久化。
- [ ] 登录成功默认工作台 / 今日销售，退出确认后返回 LoginPage。
- [ ] Tabbar 与 Content 间距达到要求且无 window/body 整页滚动。
- [ ] 通知、AI 助手、用户菜单和退出确认达到交互与可访问性要求。
- [ ] AI 助手复用 `ai_center_assistant`；个人中心和文档来自新增 hidden navigation metadata。
- [ ] hidden 页面不出侧栏，仍可被统一 navigation 查找和打开。
- [ ] Tab、Breadcrumb、Content 同步且不重复开 Tab、不修改 URL。
- [ ] 没有第二套页面标题配置、`utilityPages` 或 `topbarPages`。
- [ ] 没有正式 routes、PageShell、ComingSoonPage、权限或业务页面。
- [ ] 没有真实认证、通知、AI、API、数据库、backend、old-system 或 Vercel 改动。
- [ ] lint、指定 Vitest、build、`git diff --check` 全部通过并报告数量。
- [ ] 桌面和窄屏人工视觉验收通过，截图未写入仓库，dev server 已停止。
- [ ] 页面状态未改为 `ready`。
- [ ] 完成报告使用任务指定格式；`.planning/current/**` 不列入建议暂存。
- [ ] 未执行任何上传动作。

## 16. Completion Report

实现完成后按负责人 Prompt 规定输出：

```text
## Done
## Files changed
## Commands run
## Tests run
## Context / docs checked
## Risk check
## Acceptance checklist
## git status --short
## git diff --stat
## 建议暂存文件
## 建议 commit message
## 建议 PR 标题
## 建议 PR 描述
## Next step
```

建议 commit message / PR 标题：

```text
feat(frontend): add combined UI shell and mock login
```

下一步固定为等待架构师只读审查，且不得上传。

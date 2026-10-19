# 国内仓前端交接

日期：2026-10-19；主执行角色：前端工程师。
用户明确授权直接在dev实现，不创建分支；无提交、推送、部署授权。

## 后续任务：打包单（仓库）结构

用户已选择“只做页面结构，不做示例交互”。已启用packing页签，增加5个页面专属文件、结构浏览器测试；仅保存筛选/分页/列宽界面设置，无打包示例订单、模拟装箱、业务保存或完成状态。
新增打包页不发出业务API请求，操作入口禁用。批次查询Hook增加enabled边界，打包页激活时不请求批次数据。
TypeScript、ESLint、6项既有Vitest与5项结构/批次Playwright回归通过；额外分页可见性断言后2项结构验收再次通过，最终截图已查看。构建通过（主包体积提示仍在）。
详见docs/frontend/domestic-packing-warehouse-structure.md；该任务没有改变之前批次页面的只读数据边界，没有实现打包后端。以下原交接中的“打包未实现”特指真实业务，不再表示页签结构未开放。

## Task / Workspace

仓库 C:/Users/treas/Desktop/work/SZZSBJ；dev；任务开始基线986f355bf8f4acc3e894dfbf3abc81d636570888；worktree为当前仓库；PR未创建。
开始时已有.gitignore、后端/权限/迁移代码、docs/data-registry/DATA_INTERFACE_REGISTRY.md、docs/frontend/PAGE_REGISTRY.md及表设计文件改动；本任务未编辑这些已有改动。

## Implemented

单个国内仓批次页面，复用采购看板使用的共享搜索/表格/分页/列宽/列设置/统计组件；独立类型、API客户端和Query hooks。
只消费工作区已有只读batches/summary/trace路由；不修改后端。列表筛选、排序、分页和详情可接入该契约，尚未验证真实环境部署。
收货单日期用于到仓日，缺失保持未知。缺少的产品、ItemID、负责人、装箱/出库指标显示未接入，不填假数据。
增加客户端契约测试、PMC占位测试调整、合成数据浏览器验收和可新标签打开的静态SOP。

## Files changed

- 本目录：页面、CSS、类型、API、hooks、四个页面专属组件、客户端测试、本文。
- frontend/src/router/routes.tsx：渲染现有国内仓导航路径。
- frontend/src/config/navigation.ts：本页testing/来源与既有后端权限元数据。
- frontend/src/pages/pmc/pmcPlaceholderPages.test.tsx：保留WFS/物流占位断言。
- frontend/e2e/domestic-warehouse.spec.ts、frontend/public/help/domestic-warehouse.html。
- PRPs/pmc-domestic-warehouse-frontend.md、docs/frontend/domestic-warehouse-page.md。

## Validation

执行本地TypeScript、目标ESLint、Vitest客户端/导航以及Playwright。使用node直接执行项目已有CLI，因为当前PATH没有npm；没有安装/升级依赖。
默认Playwright Chromium缺失，本地以PLAYWRIGHT_CHANNEL=msedge使用已安装Edge；CI未设置该变量仍用默认Chromium。
早期测试失败涉及fixture envelope类型、测试拦截误匹配/src/api模块、图标可访问名称和排序下拉定位；均作为本任务修复，不修改共享组件。
最终结果：TypeScript通过；目标ESLint通过；Vitest两个文件共6项通过；Playwright三项通过（本机Edge，合成数据）；Vite生产构建通过。构建提示主包体积超过500kB，此任务不做无关的全站打包重构。
命令：node node_modules/typescript/bin/tsc -b；node node_modules/eslint/bin/eslint.js <本任务文件>；node node_modules/vitest/vitest.mjs run <客户端测试> <PMC占位测试>；node node_modules/@playwright/test/cli.js test e2e/domestic-warehouse.spec.ts --workers=1；node node_modules/vite/bin/vite.js build。
已查看稳定状态下截图，确认桌面表格可读、横向滚动限制在表格内部；窄屏包含性由浏览器断言覆盖。没有宣称真实业务数据联调通过。

## Context / docs checked

AGENTS、frontend/AGENTS、UI规则/组件目录/设计规范、采购看板实际代码、pmc_domestic当前schema/router、Ant Design 5.29.3官方Table/Tabs、TanStack Query v5取消请求文档。
使用项目内 skills/react-component-architect/SKILL.md 完成组件拆分；未新增外部Skill依赖。

## Risks / Explicitly not implemented

无数据库、.env、真实业务API、旧系统、依赖或迁移修改。既有权限体系未变；客户端不能替代后端数据权限。
打包、审批、对账未实现，仅待开放页签；通知与导出不在范围。未完整接入的指标不可宣称国内仓业务已上线。
来源观察时间由接口meta展示，不等于全系统统一快照版本；未来跨指标一致性需后端契约支持。
注册总表任务开始已有改动，本次以独立页面实施记录保存消费契约，后续合并评审需核对总表最终版本，不覆盖他人记录。

## Rollback / Next step

仅撤销本清单，保留既有采购、后端及.gitignore改动；无业务数据需要回滚。不创建/删除worktree、不提交推送。
下一步联合验证后端已部署契约和账号权限，再逐项接入缺少的字段；保持testing。

## 后续页面调整（2026-10-19）

打包单（仓库）按用户确认仅完成页面结构，无示例交互、打包业务请求或真实写操作；实施记录见 docs/frontend/domestic-packing-warehouse-structure.md。
批次筛选按截图改为两行：店铺、负责人、六种业务状态、类型搜索/批量入口/蓝色搜索按钮、收货单日期、更多筛选；第二行重置、统计显隐、列设置、禁用导出。
业务状态后端尚不支持，选择时阻止查询并清空结果，明确提示未接入；不发送虚构参数。关联状态和排序移入更多筛选。SKU、采购单、收货单支持最多50项去重精确查询，入库单使用综合匹配。负责人和ItemID/GTIN/MSKU禁用，店铺暂按ID输入。
ConnectedSearch与CommittedSearch新增可选searchButtonText/batchPlacement，原消费者默认样式和顺序不变；新增共享组件测试与目录登记。
最终回归通过：4个Vitest文件16项（含采购看板）；2个Playwright文件6项（含打包结构）；TypeScript、目标ESLint、git diff --check及生产构建。已查看最终1920px筛选区截图；构建仍提示既有大包警告，Vitest有jsdom伪元素样式未实现提示，均未导致失败。
无后端、数据库、权限模型、旧系统或.env修改；保留其他未提交改动，不提交、不推送。

## 店铺与当前负责人下拉增量（2026-10-19，覆盖上文对应待接入项）

负责人已明确确认“同意补齐后端，按当前产品负责人”。数据源决策为 docs/data-sources/decisions/pmc-domestic-filter-options-decision.md，施工图为 PRPs/pmc-domestic-filter-options.md。继续dev，不提交/推送；保留其他工作区改动。

### Done / Files changed

- backend/app/modules/pmc_domestic/{schemas,repository,service,router,registry}.py：GET filter-options、稳定ID/UID选项、列表/统计共同owner_uid筛选。沿用现有权限与账号范围，不依赖Listing权限，不读旧库/ODS/RAW。
- frontend本目录类型、API、Query hook、DomesticWarehousePage及DomesticToolbar：ReportFacetSelect搜索、多选确认、清除/重置、50项限制、加载失败重试、用户范围缓存；打包页不发选项请求。
- 后端test_read_service/test_router、前端客户端测试与两份国内仓E2E；API文档目录增加PMC真实契约及对应目录测试；nav来源登记扩充。
- 正式决策/PRP、.planning/current、API Markdown、数据接口与页面登记、SOP、页面实施文档和本文。未更改新表/迁移、外部集成、权限策略或他人的其他代码。

### Commands / Tests

使用现有node直接运行CLI，未安装依赖。pytest tests/modules/pmc_domestic -q -p no:cacheprovider（SQLite内存合成数据）13项通过；Vitest客户端/共享搜索/PMC导航/API目录4个文件13项通过；Playwright批次6项+打包结构2项通过；新增多选流程截图再次单项通过。TypeScript、目标ESLint、目标ruff、5个后端文件mypy及Vite构建通过。构建仍有既有大包提示。选项错误测试按失败开关模拟，适应开发模式取消/重新挂载请求；窄屏检查等待Drawer关闭动画后再测，不以固定sleep遮盖问题。

### Context / docs checked

项目规则、数据分层与字段标准、现有采购/Listing和实际国内仓契约。使用项目内skills/backend-module-designer/SKILL.md与skills/react-component-architect/SKILL.md分层；未引入外部Skill依赖。核对SQLAlchemy 2.0 Select/group_by/having、FastAPI query parameter model官方文档；本地实际类型检查验证安装版本。

### Risk / Acceptance / Next step

可见批次店铺跨平台覆盖，名称缺失/歧义展示ID；当前负责人通过同账号+SKU唯一active身份匹配，同名不同UID不合并，歧义/缺失不猜。列表和统计同条件，不用当前页凑选项或统计。行内负责人展示仍无契约，六种业务状态仍待后端支持，保持testing。
无真实数据库/生产连接、.env、外部API、业务写入、迁移或部署；仅测试创建SQLite内存库。新接口继承现有权限，无新增角色/授权策略。无业务数据回滚；撤销本切片明确增量即可，不撤销国内仓已有其他代码。
下一步在获准的测试环境验证已有五张表及数据新鲜度、账号范围与实际查询计划；本任务不运行真实同步或连接生产环境。

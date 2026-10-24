# 国内仓打包单审批本地 M1 交付验证

2026-10-20；实施分支dev，未新建分支、未提交推送。负责人授权按草案和审查优化开发，并强调仅本地数据库。本轮没有连接生产数据库、修改生产代码/配置或调用供应商写接口。状态为本地已实施/testing，非生产ready。

## 已交付
候选列表/汇总/选项，approve/reject、已审列表/详情/审计共8个端点；前端真实API、筛选/分页、数量及原因弹窗、权限按钮、刷新/错误重试、历史审计。读权限与写动作独立，来源账号隔离；本地DB目标保护。只有本地验证单is_test=true，M1没有OWS/AD/manual/void/装箱和六态投产。

## 本地迁移与逐表影响

| 表 | 本轮动作 | 最终情况 |
|---|---|---|
| ops_domestic_pk_sequences | 新建，北京日全库统一发号 | 1行，当日last_value=3 |
| ops_domestic_packing_orders | 新建，本系统决策与来源快照 | 4行：3通过、1驳回；均本地验证 |
| ops_domestic_packing_allocations | 新建，来源库存分配 | 3行，各分配1件；与通过订单一致 |
| evt_domestic_packing_events | 新建，不可变事件与幂等结果 | 4行，每订单一条；trigger禁止修改删除 |
| app_permissions | 新增2条动作定义 | packing-approve、packing-reject；未自动授予任何角色 |
| gov_domestic_board_publications | 从已有成功ODS本地重新发布库存证明 | 1→2行，仅1个current；保留旧版 |
| mart_domestic_inbound_batch_board | 无DDL，builder v2增加payload规范化良品/锁定/可用字段，发布新版本 | 总1454→2908，当前有效仍1454 |
| app_users、app_roles、app_role_permissions等IAM | 不改用户、角色、授权或会话 | 用户29；未创建测试登录会话 |
| 采购DWD/DWS、DIM、ODS | 仅读取 | 采购看板867，来源库存未因测试审批改写 |
| dwd_domestic_receipt_batch、dwd_domestic_receipt_batch_link | 无读依赖、无修改 | 仍0/0 |

本地Alembic从20261020_0049_domestic_inbound_board升级到20261020_0050_domestic_packing_approval，0048/0049未改。0050应用后仅增加静态检查注释和排序import；已应用DDL文本/逻辑未改，不重跑迁移。模型补全已建索引/约束元数据，无额外DDL。升级前已做全库custom-format备份并校验pg_restore目录；保留在Git外安全artifact，不上传。

已成功发布入库库存证明，不是重新采集领星；source_observed_at仍为原采集时间。GET不读ODS；库存上限来自发布的good_num-storage_used_lock_num，再减本地分配。旧审批历史覆盖未齐全，因此禁止生产和正式非测试写入。

## 真实验证结果

- 后端最终57 passed、3 skipped、1 warning；包含真实PostgreSQL外层事务回滚的合成来源测试：跨ItemID共享库存、严格整数、超量拒绝、相同/不同幂等payload及actor、来源版本/发布时间变化、页面权限不能审批、驳回终态、事件不可修改、发号999上限、审计失败时订单/分配/计数器原子回滚。测试资料未提交到业务来源表。
- 使用真实本地候选并发HTTP：相同幂等请求同时提交200/200但同一订单/PK；不同幂等键同候选200/409；只产生两条本地验证审批，PK不重号。
- Playwright Edge：真实页面→短时loopback后端→真实本地PostgreSQL，列表/通过/驳回/历史审计完整流程1项通过；独立UI契约测试（只读权限禁用动作、失败可重试）2项通过。真实页面流程增加1通过+1驳回，保留4条完整本地审计，无删除/清理掩盖结果。
- 前端单元测试6项通过；npm run build成功（既有大包体积warning）；最终npx tsc -b及本轮6组件ESLint均通过。实际backend配置下本轮6模块/权限文件/迁移/测试Ruff通过。
- 真实本地DB只读Route测试6个GET均200，当前summary：pending44、overdue35、blocked6、approved3、rejected1。库存分配与事件条数关系全部一致。所有同步/定时配置仍关闭。
- Navicat脚本9条查询实际只读执行成功。运行服务8011及Vite5173匿名请求均401，未使用真人密码/会话。OpenAPI schema注册8端点，公共OpenAPI路由沿用项目关闭策略。
- 联调鉴权是仅测试进程的合成Principal和primary scope，不是伪造生产/真人会话，也不等同真人已登录浏览器验收；正式代码未开放鉴权旁路。短时8012测试进程已退出。

前期遇到的检查问题均已修复：事务Connection/Engine绑定读取；时间同一瞬间UTC与+08表示引起指纹误变化；测试网络拦截误匹配源码路径及初始批次响应meta不完整；AntD按钮中文字间距与关闭Modal的Form连接警告。最终以通过结果为准。默认Chromium不存在，改用本机已有Edge，未安装额外浏览器。

## 验收操作
正常登录本地系统→PMC→国内仓看板→打包单审批。查看真实候选和资料不足原因；有独立动作权限可审批，本地测试单会保留真实事件。审批记录可查看3通过/1驳回及审计来源。普通角色未自动获得权限，需在现有角色管理配置对应动作；超级管理员沿用已有权限模型。

SQL：docs/delivery/local-packing-approval-verification.sql。SOP：docs/sop/pmc-domestic-packing-approval.md。API：docs/api/pmc-domestic-packing-approval-api.md。来源决策、PRP、registry、模块目录和帮助页均同步。前端保持testing，不宣称完成生产迁移/历史覆盖/OWS联动。

回滚不得物理删除已写事件或让downgrade清空审计；需要在核对后续本地改动后使用备份恢复本地。禁止向生产恢复本地验证库。

备份大小7991347字节，SHA256 `ede2a6f0a53d1978faf7e51fe24dacb00752a02c63f3846523fb0152b5a5fcc2`。详细安全证据为Git外packing-approval-20261020/migration-evidence.json、concurrency-evidence.json、final-evidence.json及approval-live.png。

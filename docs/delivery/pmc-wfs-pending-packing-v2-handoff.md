# WFS 待发货打包单 V2 本地交接

日期：2026-10-29；分支 develop_backup；状态 testing，未提交、推送、部署，不标 ready。

## Done

当前入口：待发货打包单勾选 PK → 创建 WFS 货件 → 发货箱数/计划票数/逐票箱数 → 核对分箱 → 发货信息 → 确认创建。程序自动审批，无人工审批按钮。多 PK 仅允许相同来源账号、店铺和测试标记；支持部分箱数、混合箱规、尾箱，使用实际装箱件数。OWS 非必填、探测可选。

服务端保存确认快照、自动审批时间和不可变审计，逐箱唯一占用；幂等和事务锁防重复创建。创建结果可重新打开查看。未知结果只核实；箱唛失败只补取；取消未提交表单不写入。已有占用禁止改箱/身份/报关，未占用 PK 保留国内仓改装箱弹窗。旧三 Tab 不作为创建入口。

## Files changed

- backend/app/modules/pmc_wfs：allocation、creation_schemas/models/service/router/worker、gateway、tasks；既有列表和占用守卫兼容逐箱占用。
- backend/alembic/versions/20261029_0068_wfs_creation.py：新增4表、唯一约束、外键、事件不可变触发器；有记录时拒绝降级删除。
- main / model_registry / alembic env / permission_catalog：仅必要路由、模型和动作注册，不自动赋权。
- frontend/src/pages/pmc/wfs：CreationDialog、CreationRecords、creationApi、PendingCustomsDialog及页面/类型/测试。
- 专属 pytest / Playwright 配置与 fixture、API 文档、SOP、帮助页、数据中心接口索引及增量登记。

## Commands run / Tests run

使用 backend/.venv/Scripts/python.exe 执行专属 pytest、Ruff；使用 Node 24 执行 Vitest、tsc -b、ESLint、Vite build、Playwright e2e/wfs-v2.config.ts。测试最终结果见本文后续验收记录。

隔离 PostgreSQL 14 位于本次任务临时目录，仅监听127.0.0.1:56543、数据库wfs_v2_test_run。V2表通过实际 Alembic upgrade 建立；历史来源表仅以合成 fixture 建模，不代表完整历史迁移链验收。未运行可能读取业务库的原 test_pending.py fixture。

真实浏览器→本地 FastAPI→PostgreSQL，只有平台适配器和测试登录主体替换。未验证真实 Walmart、真实用户授权分配、Redis/Celery broker投递或部署。同步测试dispatcher不等价于真实队列验收。

## Context / docs checked

项目规则、既有 V2产品/开发需求、数据源决策、数据库分层/字段标准、布局和复用规范、独立本地PRP。前序实现核对 Walmart 创建/标签官方契约、SQLAlchemy 2 session、Pydantic validator、Celery任务说明；外部写契约与账号能力仍需适配器专项确认。

## Risk check

- old-system/旧项目只作参考，未修改。
- 仅连接任务专属测试库；未迁移现有业务库、生产库。
- 未修改.env、公共CI、全局忽略、公共启动脚本、公共调度或历史迁移。
- 未调用真实Walmart或领星API；测试替身只在tests目录。
- 新增动作权限定义，不授予用户/角色；后端仍校验数据范围。
- 无外部Skill、无子Agent、无部署。

## Acceptance checklist

- 本地创建和自动审批链路、部分箱数、混箱尾箱、多PK、并发幂等、旧占用、防越权、未知结果与标签恢复有专属覆盖。
- 自动审批成功与平台创建成功分别展示；默认真实Gateway禁用，不伪造成功。
- 默认正式页面确认创建仍不可执行，必须明确提示能力尚未启用。
- 改装箱复用国内仓服务；本次浏览器仅验证读弹窗和取消，未放宽国内仓数据库写入保护。
- API/SOP/帮助、来源、权限及回滚边界已补充。

## Next step

真实平台适配器及生产前验收尚未完成。后续须完成平台商品/退货地址/ITS/创建幂等与核实契约、真实沙箱适配器、Celery投递及恢复验证，再安排授权的业务库迁移与环境验收。不得将本地fixture货件当作真实WFS创建。

代码回滚保留已创建事实和审计；不可通过删除占用重发。四表有业务记录时migration downgrade主动阻止；恢复方案需专项核查。


## 最终验证与用户环境故障（2026-10-29）

- 后端13项通过（含缺表明确503）、Ruff通过；前端4项待发货单元测试、10项WFS导航/页面回归通过；tsc、定向ESLint、Vite构建通过。构建有既有大包警告；jsdom有伪元素样式提示。
- 实际隔离链路Playwright 2项通过：30箱发20拆12+8、自动审批、箱唛下载、刷新后剩10箱、占用禁止改箱；另一PK改装箱弹窗、添加尾箱行、取消不写入。真实Broker、真实Walmart、改装箱提交未验证。
- 用户报告 localhost:5173 页面请求失败后，只读检查本地 szzsbj_dev：版本20261028_0062_packing_pending_edit，四张V2表均不存在。新版列表查逐箱占用表导致失败；不能视为无数据。
- 已补WFS_SCHEMA_NOT_READY（503）和中文缺迁移提示，并以本地只读查询确认。没有创建表、写业务数据或修改Alembic版本。
- 0068依赖0067合并头，直接upgrade将引入另一迁移链（AI运行、Listing评估、Monitor投影等），不能在本任务默认授权下执行。必须先确认本地迁移范围；页面尚未恢复可用。
- 风险记录更新：除隔离测试库外，为排查用户故障只读连接本地szzsbj_dev检查表名和版本；没有读取业务明细、生产数据或显示密钥。


## 本地完整迁移执行结果（2026-10-29，覆盖前述待批准状态）

### Done

用户明确授权“允许在本地开发库执行这条完整迁移链”。已核对127.0.0.1:55432/szzsbj_dev，执行8个既有迁移步骤：费用检测证据0061、同步异常0062、AI运行0063、Skill上下文0064、Listing评估0065、Monitor投影0066、合并头0067、WFS创建0068。当前唯一版本为20261029_0068_wfs_creation，四张WFS表存在。未改写历史迁移、未stamp跳过步骤。

### Files changed

本次只追加交接、PRP批准记录和任务登记；数据库通过既有Alembic迁移改变。当前分支develop_backup，既有工作区改动保留，未提交推送。

### Commands run

local_url严格身份检查；pg_dump --no-password --format=custom；pg_restore --list；alembic.command.upgrade(Config('alembic.ini'), '20261029_0068_wfs_creation')，设置10秒锁等待、120秒语句超时；迁移前后只读检查版本、四张表及来源表数量。

备份：C:/Users/treas/.codex/backups/wfs-local-20261029-113312/szzsbj_dev_before_wfs.dump（8,869,186 bytes），归档目录校验通过；manifest.json保存前后版本和表数量。未做恢复演练。此前两次未完成备份未用于迁移；成功备份后才执行DDL。

### Tests run

使用完整create_app、TestClient和真实本地数据库只读事务验证orders、summary、filter-options、capabilities均200，待发货total=0，creation_enabled=false。测试登录主体仅进程内替换，不修改真实权限，不代表已验证用户浏览器会话。迁移前后国内仓打包单、装箱集、装箱行、历史WFS草稿记录数一致。

### Context / docs checked

AGENTS.md、AI_DAILY_RULES.md、本地数据库保护脚本、Alembic env及完整迁移依赖。用户授权仅本地完整链；不扩展到生产或平台执行。

### Risk check

- 本地库：已授权迁移；生产库：未连接/修改。
- old-system、.env、密钥、公共启动脚本、CI及调度：未修改。
- 真实外部API、部署、重启生产服务：未执行。
- 权限：未授予或变更用户权限；本次不启用新模块调度/AI任务。
- 外部Skill：未使用。

### Acceptance checklist

已排除WFS缺表错误；本地真实数据读接口通过。零待发货记录为实际查询结果，不以示例数据补空。真实Walmart适配器仍禁用，创建真实货件尚未验收。

### Next step

用户刷新localhost:5173/#/pmc/wfs/pending-packing确认页面。若仍报错，按该请求的状态码/request_id继续定位；不要重复迁移。真实Walmart适配器和队列验收仍按前述独立范围推进。

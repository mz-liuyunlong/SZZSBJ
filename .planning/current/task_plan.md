# Develop 全量 CI 修复（2026-10-27）

负责人授权复用 develop，提交、推送并创建 develop → main 草稿 PR；不合并、不部署、不连接生产。

- [x] 核对分支、远端祖先和已有工作区；修复 Ruff、ESLint、文档规则错误。
- [x] 修复表结构检查使用独立连接导致事务回滚的问题；保留安全断言。
- [x] 前端 304 项单测、lint、构建通过；采购覆盖及迁移对照 15 项通过。
- [ ] 推送 develop，创建指向 main 的草稿 PR，核对全部远端 CI。

以下为历史任务：

# 国内仓迁移安全补充验收（2026-10-22）

负责人授权直接在 dev 修复，不新建分支，不新增 0055；确认旧版 0054 从未执行。
- [x] 核对 dev/c76208c 和干净工作区，读取数据库规范
- [x] 补齐 ODS/0053/0054 约束和索引接管校验
- [x] 测试库随机命名、所有权保护、独立 CI 强制配置
- [x] PostgreSQL 空库/0049/已有表漂移/OWS 阻断/业务读写验收：56 passed，0 failed/skip
- [x] 修复报告、版本链、20 表清单及负责人审核交接；未提交/推送/部署

以下为此前任务历史，不代表本轮工作分支：

# 国内仓当前修订修复

不新增修订号。分支 `codex/domestic-chain-current-revision-fixes`。

- [x] 在现有 0054 中创建 `ops_domestic_packing_extra_allocations`
- [x] 0053 已存在仓库表时核对字段和主键，不一致则停止
- [x] ODS 接管区分 timestamptz 与 timestamp without time zone，并核对 varchar 长度
- [x] 用一次性本地库验证，不升级 szzsbj_dev

# 国内仓筛选选项

用户已确认方案及当前产品负责人语义。仅本国内仓模块增量，保留已有工作区修改，继续dev。

- [x] 核对来源并固化数据源决策、已确认范围PRP
- [x] 后端选项与owner_uid筛选
- [x] 前端ReportFacetSelect与选项hook
- [x] 测试、文档、登记与交接

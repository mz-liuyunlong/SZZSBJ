# 打包审批剩余三项整改

范围：develop 上的 PMC 打包审批、采购证据读取及对应测试。列表继续隐藏审批通过/驳回，仅保留修改。未修改任务中心、统一调度、其他模块业务代码、表结构或迁移。本次没有提交、push、更新 PR 或部署。

## 修复和影响

1. `packing_rules.py` 增加公共 Listing 阻断规则，供 `packing_repository.py` 候选投影和 `packing_service.py` 最终校验共用。已发布、WFS、非空链接、有效 GTIN/MSKU 才符合 Listing 条件；空链接及纯空白链接返回既有 `ELIGIBLE_LISTING_MISSING`。库存、来源版本和权限等其余条件保留。
2. `packing_service.py` 的 approve/reject 两种终态都删除修改草稿，仍在正式订单、不可变快照与事件提交的同一事务中操作；失败保留草稿和原审批记录，幂等重放复用正式结果。
3. `packing_repository.py` 只读取当前候选关联的账号/采购单/SKU 明细；计划分摊分母通过数据库分组汇总，包含同计划其他采购单，不能按当前可见采购单缩小分母。候选占用/决策排除仅查询相关 board ID，决策排除读取五个身份字段，不载入历史 JSON 快照。`packing_procurement_repository.py` 的采购/计划 ODS 用账号与单号联合过滤，权重计算按账号/SKU/店铺/采购单索引，不再为每个候选扫描全部明细。

`packing_stock_repository.py` 没有改动：SKU 全局预算仍统计请求 SKU 的全部占用，包括旧快照或消失来源上的占用。不能将候选查询的 board ID 限制错误复制到全局预算，否则会释放真实库存占用。

## 实际验证

```powershell
cd backend
.venv/Scripts/python.exe -X utf8 -m pytest tests/modules/pmc_domestic -q
.venv/Scripts/python.exe -m ruff check app/modules/pmc_domestic tests/modules/pmc_domestic/test_packing_query_scope.py tests/modules/pmc_domestic/test_packing_suggestions.py tests/db/test_packing_pending_edit_postgresql.py
```

国内仓测试：120 passed、62 skipped；跳过项需要显式启用的隔离数据库/集成环境，不能视为验收通过。修改文件的 Ruff lint/format 检查通过。

新增合成回归检查：1/500 个候选下，候选主体查询均为 14 次（测试替换了身份映射和库存预算，不能当作完整 HTTP 请求总数）；采购过滤绑定包含账号/采购单/SKU，跨采购单计划分母保持完整。1/1,000 个 SKU 的库存预算均为三次批量查询，并计入孤立来源占用；10,000 个无关 SKU 分组不被当前权重计算遍历。这些验证查询范围与算法复杂度，不代表真实 PostgreSQL 执行时间或生产容量。

`tests/db/test_packing_pending_edit_postgresql.py` 在既有空库/0049/0061 三个隔离迁移场景中补充：保存草稿→驳回→草稿删除、正式记录/快照/事件保留、库存占用不增加、重复请求不重复写、提交异常时草稿及审批记录一起回滚。

本机 Docker 引擎未运行；本轮尚未运行上述 PostgreSQL 专项，也未执行 EXPLAIN 或真实数据规模压测。没有连接现有业务库替代。远端 CI 结果仍属于此前提交，本地本轮修复需经负责人确认提交/push 后由隔离 CI 验证，不使用 skip 结果宣称数据库通过。

## 文档与审核

核对 SQLAlchemy 2.0 的联合键 IN 用法：[官方操作符文档](https://docs.sqlalchemy.org/en/20/core/operators.html#tuple-in-expressions)。没有增加依赖或索引。当前最终迁移仍为 `20261028_0067_merge_pmc_main`，本轮迁移目录无 Diff，等待统一审核。

剩余限制：候选列表仍需遍历授权范围内的当前发布候选以得到准确过滤与汇总；相关采购单的 ODS 历史版本仍按既有最新成功版本规则读取。此次没有改写去重口径，也不承诺任意数据量下固定加载耗时。后续如隔离 PostgreSQL 执行计划发现需要新增索引，应另提方案交数据库负责人审核，不擅自增加迁移。

## 公共边界复核（2026-10-28，业务修复提交之后）

业务修复已提交为 `9ddca54a5cb588b7c8d7a4b9a493ab434afd1b48`，对应 push CI run `40662612594`、PR CI run `40662618946` 均为 12/12 任务通过，包含隔离 PostgreSQL 专项。此前“尚未提交/未运行”的描述是本地修复阶段记录，不再代表该提交的远端状态；不将任务成功数量当作测试用例数量。

负责人本轮要求仅清理公共文件边界和说明。最新 main 为 `2ef4fd1d6606a85017046f75b796a1dfdbe28e19`；Git fetch 连接重置后，通过 GitHub Contents API 按该完整 SHA 读取以下五份文件，并校验 Git Blob SHA。未合并 main、未覆盖其他业务文件。

| 文件 | main Blob | 本轮处理 |
|---|---|---|
| `backend/scripts/start-local-api.ps1` | `aae17b8cbb6eddc91ef052e9fc9851c53cece18e` | 逐字节恢复 main，包括原有 8011 端口；未运行启动脚本 |
| `.gitignore` | `cf88229091e961e9e5976e571a0aa43f632d8d9a` | 逐字节恢复 main；个人 `.planning/` 仅写入本地 Git exclude，不提交全局忽略规则 |
| `docs/tasks/TASK_REGISTRY.md` | `a2df47fd07aabfa93bd01a7cb456c902ef6d3011` | 原始 main 内容及 `domestic-chain-0054-safety-review` 整行恢复；本 PR 在独立小节登记，不改原验收结论 |
| `docs/api/README.md` | `6144a3c532a0125e5b2536b1341d7f4ea7290aa2` | 仅删除本分支新增的 Walmart Monitor 重复条目，保留 main 原条目与 PMC 条目 |
| `.github/workflows/ci.yml` | `0c322d019cf00d55ac90f73ac1d7e83c4e3699b5` | 当前差异单独列出如下，处理方式等待负责人明确审核 |

现有公共 CI 差异：

1. push 分支列表增加 develop；pull_request 仍以 dev/main 为目标。
2. 仅国内仓 PostgreSQL job 增加 Redis 7 service，映射 6379 及健康检查，用于跨进程口令失败预算测试，不是业务调度配置。
3. 国内仓步骤名称更新，并在既有 pytest 命令加入 `tests/db/test_packing_pending_edit_postgresql.py` 与 `tests/db/test_packing_passcode_redis.py`；保留 JUnit 不允许专项 skip 的检查。

本轮不再修改工作流，除非负责人明确选择撤回；不以 PMC 业务修改授权代替公共 CI 审核。新增测试可以保留，是否由公共工作流接入由负责人决定。

本轮没有更改迁移、PMC 业务实现、统一任务中心或调度器；没有运行启动脚本、读取真实环境配置或接触生产。当前文件修正尚未提交/push，新提交的远端 CI 需要另行确认后执行，旧提交绿色结果不覆盖本轮边界修正。

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

# 国内仓打包审批数据源决策

2026-10-20；READY_FOR_PRP（本地 M1）。负责人本轮明确要求按开发计划和审查优化内容实施、本地建表并前后端联调；沿用dev保留现有改动，不操作生产。批准范围不包含领星写接口或生产部署。

来源证据：交接20261019 §4/5.2、旧review_server/server.py dom_validate及dom_state仅只读参考。旧运行时接口/事件文件不接入新系统。原计划是候选草案，本决策与实现PRP优先。

| 数据 | 权威与读取层 | 写入方与边界 |
|---|---|---|
| 采购入库来源 | REBUILD_SYNC；当前gov_domestic_board_publications及入库MART，粒度账号×惠州仓16168×入库单×SKU×店铺 | 现有发布器，不依赖空的收货DWD；M1不扩展AD调拨 |
| 良品和领星锁定量 | 既有成功批次ODS中good_num/storage_used_lock_num，经现有builder规范化写入新发布MART payload | GET不查ODS、不调领星；旧版本缺字段时阻断审批；保留历史版本 |
| Listing | 既有DIM，账号+店铺+SKU匹配，PUBLISHED且fulfillment_type为0/1，GTIN/MSKU作为商品快照 | 没有或冲突明确blocked，不跨店猜归属 |
| 到货情况 | 采购DWD按原采购行去重计算采购量；收货DWD当前为空，已到/未到及arrival状态未知 | 不把采购计划拆行重复累加，不把未知当0；不实时回查ODS |
| 报关默认 | 当前标准资料未提供可确认purchase_remark，默认未知 | 用户明确declare/skip可落库manual；default保持未知，不伪造auto |
| PK/审批/分配/事件 | NEW_SYSTEM_OWNED，OPS与EVT | 服务单事务；只写local LOCAL_DATABASE_NAME，无外部调用，无Celery任务 |

切换安全：本轮全部写入为is_test=true的真实本地验证记录；不声称覆盖旧审批历史或领星OWS。缺完整历史审批覆盖时不开放生产业务写入。服务验证环境及实际连接目标，拒绝生产/非本地写入。默认驳回为终态；manual/void/link/AD留后续切片。没有把旧口令白名单移植到新系统。

退出条件：后续生产PRP单独确认历史审批覆盖、OWS关联、库存新鲜度策略、人工编辑/撤销和投产发号衔接。不得直接把本地验证记录迁入生产。


> 占位名称说明：`LOCAL_DATABASE_NAME` 与 `ISOLATED_TEST_DATABASE_NAME` 分别表示负责人已批准的本地开发库和隔离测试库；执行前必须与获批本地配置中的实际数据库名逐字核对，并同时核对环境、host、port及连接后数据库身份。占位名称不是可直接执行的数据库名，也不授权其他本地库或生产库。历史数量、指纹及备份哈希保持原记录。

# PMC仓库打包本地PRP

当前开发与本地模拟联调已完成，负责人确认先不接真实领星。权威规则见docs/data-sources/decisions/pmc-packing-warehouse-decision.md；接口契约见docs/delivery/pmc-packing-warehouse-api.md；操作见docs/sop/pmc-domestic-packing-warehouse.md。

范围为当前dev和本地szzsbj_dev，不新建分支、不提交推送、不触及生产、不运行全局业务回归。导航布局保持负责人最新要求。

本轮仓库三种数量情况、原审批与额外分配、幂等事务、异常/通知任务、IB登记、模拟同步与人工再确认、来源快照已实现。本地35项后端和2项模拟页面联调已通过；真实同步未配置、外部推送及货件/箱规写入不在本轮验证范围。未来真实网络采集必须复用治理发布链，不能在业务GET或持锁事务里调用。

独立动作与来源账号范围在服务端校验。没有自动授权用户角色；中台补IB/同步与仓库完成分开。extra_allocations记录逐入库源额外数量，原Q不变，审批余额扣同一预算，发布切换不清空历史有效占用。修改与异常均保留不可变事件。

新增表/事件约束本地SQL先备份后应用，保持0052；生产发布前需另行整合正式Alembic迁移并验证从线上基线升级，此PRP不授权生产部署。

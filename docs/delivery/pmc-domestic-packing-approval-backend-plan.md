# 国内仓打包单审批 · 开发计划与实施状态

2026-10-20；原草案已按审查意见修订，并由负责人授权在现有dev实施，本地M1已完成代码与建表，保持testing，真实验证结果见pmc-domestic-packing-approval-verification.md。不创建分支、不提交推送、不访问生产。

## 已实施范围
候选、汇总、店铺选项、审批通过/驳回、已审批记录与审计详情，前端联调。候选来源为入库MART及当前发布版本，关联账号/惠州仓/入库单/SKU/店铺/ItemID，不依赖空收货DWD。良品和锁定量由同源成功批次ODS经发布器规范化进入MART payload，GET不回查ODS、不调领星。

## 四张新表
ops_domestic_pk_sequences（统一北京日发号）；ops_domestic_packing_orders（决策及商品/来源快照）；ops_domestic_packing_allocations（同源库存分配）；evt_domestic_packing_events（幂等与不可变审计）。原草案三表方案已被四表替代，M1即防跨ItemID超分配。关联使用publication_id+board_id复合来源外键，保留历史发布。

## 规则与权限
本地验证单固定is_test=true；通过必须合法正整数、资料完整、可用量足够且来源版本未变。驳回非空原因、终态不得再审。操作权限独立于页面查看权限；首次序列创建及并发发号原子化；命令幂等与候选去重均在事务锁内。默认报关资料未知，不伪造采购备注；收货列缺标准事实显示未知。来源时间、审批时间、到仓日分别保留。

## 本地执行顺序
已形成READY_FOR_PRP来源决策、实施PRP和API契约，新增0050接当前本地0049后，未改0048/0049。先备份并核对pg_restore目录，再迁移四表与两条权限定义；本地从既有ODS重新发布库存证明，不重新拉领星、不改ODS/DWD/DIM/采购/用户/角色授权。旧发布保留，当前1454行不变。

## 后续切片
manual、AD调拨、作废/重提、编辑、更换链接、仓库装箱、OWS link、六态看板、领星写入和生产部署均未纳入本地M1。生产写保护保持关闭，未来须先解决历史审批覆盖、OWS关联、库存新鲜度和发号衔接。

## 权威文档
- PRPs/pmc-domestic-packing-approval-backend.md
- docs/data-sources/decisions/pmc-domestic-packing-approval-decision.md
- docs/api/pmc-domestic-packing-approval-api.md
- docs/sop/pmc-domestic-packing-approval.md
- docs/delivery/pmc-domestic-packing-approval-verification.md

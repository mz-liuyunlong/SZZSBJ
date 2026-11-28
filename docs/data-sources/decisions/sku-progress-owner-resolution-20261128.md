# 新品管理负责人数据源决策（2026-11-28，本地候选）

## 问题与范围

0100 原列表投影仅包含 Listing MART 的 `owner_ref`；为空时负责人选项被排除。修复已获负责人授权；本次不改页面样式、采购、审批、推进状态、数据范围、定时任务或数据库结构。

## 数据源及身份

- 原 Listing `owner_ref` 是已有 Listing 级证据，保留原值。
- 已批准的现有模式：`backend/app/modules/walmart_monitor_targets/repository.py` 在 Listing 负责人缺失时回退至唯一当前 SKU 负责人；`backend/app/modules/data_pages/repository.py` 和新品表现也读取 `dwd_lingxing_sku_product_info_current` 中的 owner_name / owner_uid。
- 新品管理现有 read model 已持有 source_account_ref、sku_identity_id、sku、identity_verified。以其账号和已核实身份连接 `dwd_lingxing_sku_identity_index`（active、lingxing、同 SKU），再通过 provider/account/lingxing_sku_id 唯一键且核对 identity_id 连接当前 ProductInfo；不扫描 RAW，不调用领星，不读取其他账号数据。
- 对同一 Listing：若原 owner_ref 非空且与 SKU 当前名称或 UID 不同，保留原 Listing 负责人；若原值为空或与 SKU 当前负责人一致，使用当前真实姓名（缺失时保留来源值或 UID）。无证据仍为空，不把开发人员当负责人，不编造姓名。SKU 级数据不能证明不同店铺有独立分配；存在独立 Listing 负责人证据时优先保留。
- 列表新增 `owner_display`，原 owner_ref 不变；筛选 value 为账号 + 已核实 UID（没有 UID 则源值），label 与列表显示相同。列表、统计、facets 复用同一 SQL CTE；保留按 SKU 分组和既有筛选计数口径。旧的选中名称可能因 UID 规范化需重置一次筛选。
- 读取当前 DWD 而不是修改持久化投影，后端重启后无需额外刷新、迁移或生产写入。已有源数据同步仍负责更新负责人。身份不唯一时不使用 SKU 兜底；不存在负责人信息时选项仍为空。

## 验证与风险

新增 SQL 结构及合成表达式测试、前端独立 Listing 展示测试。真实环境需核对列表、负责人选项、统计、跨账号隔离、多个店铺的独立证据及接口延迟。尚未完成实际 PostgreSQL/生产验收或 CI。仅修改本业务查询及前端适配器，回滚源文件即可，无数据回滚。

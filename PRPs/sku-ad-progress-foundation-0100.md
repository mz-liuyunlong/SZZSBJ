# SKU / 广告 / Listing / SKU进度数据基础 — 0100

## 目标与范围

负责人确认：SKU与广告合法业务数据完整存储；Listing维持原有领星字段，仅新增由广告数据计算的广告状态；SKU进度新增5张独立业务表；仅建设数据库结构，不实施业务接口、同步、回填或前端。迁移从0100开始。不得改变旧数据、原有计算公式或同步行为。

- 最新 main 核对：`dac75a603b9dffe03f1c764d0413d81a94d3f32d`。正式0098为 `20261126_0098_wfs_cost_valuation_flow`，尚未核实正式0099父版本。0100源码放在 `PRPs/pending-migrations`，不参与活跃迁移链。
- 本地源代码安装不切分支、不拉取、不覆盖已有文件、不连接数据库。正式父版本确定后单独激活；不执行迁移。
- 依据 `AGENTS.md`、`AI_DAILY_RULES.md`、`docs/data-sources/database-layering-standard.md`、`docs/data-sources/field-standardization-standard.md`、`docs/delivery/backend-data-source-decision-gate.md`。本PRP仅覆盖 schema；后续接口数据源决策仍须确认。

## 数据源与结构

### SKU（5张扩展表）

复用 `dwd_lingxing_sku_identity_index` 的 UUID，采用 account+identity+interface 区分来源。不修改现有 SKU 当前表、快照表、图片/标签表、成本、业务哈希、权限或同步规则。扩展源快照保存完整脱敏业务JSON及来源请求/序号/观测时间/解析版本/hash，已盘点524条字段路径均可保存。每接口独立当前指针，避免空字段互相覆盖；未来按实际业务变化建快照，重复观察只更新指针观测元数据。数据保留应依现有政策另行确认；不把未知字段直接公开给API。

1. `dwd_lingxing_sku_source_snapshots`：源业务数据完整JSON+已知标量标准列。开发日期权威源为 ProductList 的 create_time，保存原始 epoch 与 UTC 时间；日期展示时区待确认，不使用系统创建时间。尺寸、金额、税率等新增标准值须核实单位与精度，不覆盖旧业务字段。
2. `dwd_lingxing_sku_source_current`：按来源接口关联当前扩展快照，复合约束避免错配。
3. `dwd_lingxing_sku_supplier_quotes_ext`：多供应商、多报价及采购链接。
4. `dwd_lingxing_sku_supplier_tiers_ext`：币种、含税、税率、阶梯MOQ及价格；不强行认定0为无效。
5. `dwd_lingxing_sku_country_logistics_ext`：按源记录序号+国家/地区保存物流及清关数据；不修改美国头程计算。

报关/质检/属性/组合/辅料/自定义字段/附件/巴西开票等完整嵌套数据保留在快照JSON，未来按用途提取明细；不创建几百列，不复制已有图片标签子表。字段映射见 `sku-ad-progress-foundation-field-map-0100.json`。

### 广告（3张扩展表）

保留 `dim_walmart_advertisers`、`fact_walmart_ad_item_sp_daily`、`biz_walmart_ad_campaign_catalog`、`biz_walmart_ad_item_current`、`biz_walmart_ad_item_history`、`biz_walmart_ad_ingest_cursor`。原事实表仍为花费和归因权威。51个广告报表原始字段全部具备存储目标；不重复修改财务事实，不依赖广告账户名称猜测店铺。

1. `biz_walmart_ad_account_store_mapping`：来源账号+广告账户唯一，店铺映射、证据、确认状态、观测时间；不回写现有账户表。当前生产抽查10账户均无store_id，后续核实唯一匹配。
2. `dwd_walmart_ad_item_config_ext`：来源账号+广告账户+活动+组+项+商品唯一，保留所有状态、类型、名称、竞价、审核、来源店铺/图片/链接、分时策略JSON及完整记录。广告目录当前为空，后续调查与初始化。保留现有目录，不新增第二套同步任务。
3. `fact_walmart_ad_item_sp_daily_ext`：日期+账号+广告账户+原事实行hash，与原事实表自然键对应，补CPA/AOV/关联销售/品牌新客指标，保留完整来源记录及币种。无指向原事实表的外键，避免阻塞其按天重建。后续应与事实数据一致地更新/清理扩展记录；不可把扩展表当第二份广告花费账本。

### Listing（1张独立读模型）

`mart_listing_ad_status_current` 按来源账号+店铺+Item ID唯一，ad_enabled true/false/null，判断时间、观测时间、证据、规则版本、未知原因。此独立读模型是Listing管理未来的新增字段来源，不ALTER `mart_listing_management_current`，不修改现有读路径。根据账户/活动/组/广告项状态、审核、数据完整度和新鲜度判断；具体枚举/时间窗/覆盖范围待后续确认。无数据不等于未开启。SKU进度复用Listing管理输出。没有业务状态计算实现。

### SKU进度（5张业务表）

1. `biz_new_product_sku_progress`：账号+SKU身份唯一。当前/自动/人工状态分离，人工锁定、人工依据、状态原因、备注、负责人、预计完成/下次跟进日期、进入/退出/暂停/恢复/终止/完成时间、自动规则依据、版本。系统初始行可无备注，人工判断要求非空备注，人工暂停/终止要求原因；不锁死原因枚举。暂停次数由事件汇总，不重复存储。人工与自动优先级后续确定，不能自动覆盖人工锁。
2. `biz_new_product_sku_purchase_plans`：关联进度+采购店铺，数量、请求/批次/计划单号/明细号、提交和取消状态、异常及幂等键；同SKU同店不允许并行有效首批采购请求，超时未知占用防重位。默认20为未来UI规则，不写死业务数量。成功才记录已提交，接口语义需确认。独立于测评后的采购审批，不调用领星。
3. `biz_new_product_independent_site_submissions`：支持SKU级或Listing级（显式scope与部分唯一索引）；实际启用哪种模式待负责人确定。状态、提交方式、外部商品ID/链接、人员/时间、失败及撤销。
4. `biz_new_product_sku_progress_events`：追加事件、前后快照、操作者、时间、备注、幂等事件键及证据。未来API不可覆盖历史。
5. `biz_new_product_sku_progress_milestones`：节点范围SKU/店铺/Listing/采购计划，实际发生、观测、首次确认及记录时间分离，支持更正或撤销事件；同SKU的采购计划复合外键校验。不能把首次观察当真实发生时间。

SKU进度只读取产品、开发日期、Listing、PMC、国内物流、广告状态，不单独复制源字段。国内发货、采购进度权威来源与自动完成规则仍需讨论，不影响本次schema。独立站维度待确认。

## 权限与兼容性

无新增页面、API、任务、角色、权限变更。新增表以source_account_ref或父记录隔离；后续API要落实数据范围、字段权限、操作审核。为了不改变旧表的删除或同步行为，本阶段不对旧表建立新的外键，仅通过稳定键关联并在后续服务验证。新表内部使用RESTRICT外键，禁止误删业务历史。JSON仅存储经授权、脱敏后的业务数据，不存密钥或认证信息。

## 验收与回滚

- 只创建14张新增表及16个显式索引；无对旧表ALTER/DROP/TRUNCATE/INSERT/UPDATE/DELETE，无回填，无自动运行。
- 迁移升级与ORM定义逐项离线PostgreSQL DDL比对，检查外键仅指向新表；降级仅删除新增表（上线后降级会丢失新增数据，必须单独审批和备份）。
- 0100正式迁移激活须提供确切0099父revision，且当前本地迁移链唯一head与该值完全一致。不自动占用0099或改旧迁移，不自动运行alembic upgrade。
- 真实数据库迁移测试须在隔离临时库完成，之后再批准本地或生产迁移；本包未执行数据库连接。
- 同步、历史回填、页面、接口、权限和计算口径变更全部不在本次范围。后续需独立数据源决策和PRP。

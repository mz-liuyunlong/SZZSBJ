# 国内仓收货批次补充库存：接入调查与阻塞项

日期：2026-10-19。分支：dev。状态：BLOCKED_BY_OWNER_DECISION（基本响应结构已确认，批次关联证据、库存语义及本地运行配置待补齐）；未编写同步/业务接口代码，未执行真实同步或数据库写入。

## 1. 已确认范围

用户提供领星网页库存列表接口及请求参数，要求同步到批次看板；随后明确选择：

- 保留收货批次，关联补充库存。
- 同步目标为本地开发数据库。
- 既有到仓日期仍按收货单实际收货日期，不改为库存查询日期或采购入库日期。

本文件不包含登录账号、密码、Cookie或Token。登录信息不作为代码、日志、文档、测试或RAW内容保存。

## 2. 前置调查证据

| 项目 | 证据与结论 |
|---|---|
| 用户指定页面 | https://erp.lingxing.com/erp/msupply/warehouseDetail |
| 用户指定接口 | https://erp.lingxing.com/api/storage/lists；已提供请求体及一条成功响应样本，结构分析见第7节 |
| 请求范围 | wid_list/mid_list/sid_list为空；is_sku_merge_show=0，is_hide_zero_stock=0，offset=0，length=20。不能据此认定返回粒度、仓库范围、全部数据或库存字段含义 |
| 网页访问 | 页面跳转/login；浏览器绑定/控件读取连续超时；截图为空白，尚未输入凭据或取得已登录数据 |
| 旧接口代码/旧库 | 本任务未读取旧系统或旧库；不是运行数据源 |
| 新系统读取表 | 当前API读取dwd_domestic_receipt_batch和dwd_domestic_receipt_batch_link；前者一行对应一条收货明细 |
| 既有库存存储 | ods_lingxing_domestic_inventory、ods_lingxing_domestic_batches、ods_lingxing_domestic_inventory_events；现有只读看板不直接消费库存ODS |
| 表写入方 | integration_sync/handlers/lingxing_pmc_domestic_sync.py执行分页落ODS；pmc_domestic/publisher.py从成功采购收货ODS发布收货DWD，当前仅生成unresolved关联占位，不生成库存分配 |
| cron/脚本/外部API | run_pmc_domestic_once.py及pmc_domestic_client当前显式要求production环境；本次不运行、不伪造环境、不放宽现有门禁 |
| 已登记开放接口 | inventoryDetails、getBatchDetailList、getBatchStatementList、warehouse；完整路径见pmc_domestic_catalog.py。其契约和网页storage/lists不能视为相同 |
| 人工写库 | 不新增入口，不允许按SKU猜库存分配 |
| 外部重新获取 | 既有开放接口同步能力可作候选；需要实际配置App凭据，网页账号密码不能直接当开放接口AppID/AppSecret |
| 少量配置可行性 | 不适用；库存是业务事实，不能手填名单或造示例数据替代 |
| 本地就绪检查 | 当前进程APP_ENV未设置；DATABASE_URL、领星开放接口AppID/AppSecret、PMC_DOMESTIC_SOURCE_ACCOUNT_REF均未配置；backend目录只有.env.example。仅检查配置是否存在，未打印秘密或连接数据库 |
| 短期策略 | 取得storage/lists脱敏成功响应，验证粒度、字段、分页、身份和库存口径；由用户配置本地运行连接，通过正式PRP批准后实现 |
| 长期策略 | 优先稳定、可治理的已落库来源；如需改用开放接口，必须明确核对与用户指定网页数据的字段/数量差异，不静默替换 |

## 3. 数据集决策

| 数据集 | 分类 | 结论 |
|---|---|---|
| 收货批次和到仓日 | 复用既有REBUILD_SYNC结果 | 保持当前收货ODS→收货DWD口径，不覆写实收数量和日期 |
| 网页库存列表 | NEED_OWNER_DECISION / 部分契约已确认 | code/data.list/data.total等结构已确认；仍需核对稳定行身份、数量语义、分页及可用采集入口，不默认视为开放接口的等价来源 |
| 批次库存归属 | NEED_OWNER_DECISION / 待关联证据 | 需要收货/入库/来源批次标识等明确证据，不能仅用SKU和数量推断 |
| 本地运行目标 | 已确认local，配置未就绪 | 不连接任何未确认的数据库；配置完成后先校验环境及目标，再执行本地操作 |

未解决项：库存字段业务定义、身份映射和多批次关联、本地连接/来源账号配置。网页基本响应结构已确认，不再要求重复提供相同样本。业务行粒度及环境已确认，无需重复确认这两项。
接口总体状态不是READY_FOR_PRP；此时不编写接口实现。补齐证据后更新本决策，形成具体字段、权限、迁移、回滚和分页规则的PRP，并按项目规则确认。

## 4. 候选实现步骤（待证据后具体化，不是已批准施工图）

1. 对照成功响应，记录返回路径、库存字段含义、仓库/店铺/SKU/批次ID、总数与分页终止条件；保持外部ID字符串和0/未知区分。
2. 校验本地数据库、APP_ENV=local及来源账号。凭据只由安全运行配置提供，不写入仓库、命令参数或RAW。已有生产限定脚本不可直接复用为本地执行入口。
3. 构建受控分页同步：独立run、幂等键、去重、失败/部分完成标记、来源快照时间；仅完整成功快照可发布，保留旧的完整快照。
4. 经过RAW/ODS及标准化后发布供看板读取的DWD或read model；不让前端直读外部接口/RAW/ODS。复用或新增表由字段和粒度证据决定，此时不承诺表数量。
5. 收货批次按明确来源单据/明细证据关联库存。若只能得到仓库+SKU/店铺汇总，则标明是该维度总库存，不能当每批余额，不能在多条收货批次上重复累加；批次余额继续未知。
6. 既有API扩展经过字段标准化和源权限校验，列表/统计同口径；到仓日期和实收数量不变，缺失关联明确待核实。
7. 合成契约/分页/幂等/账号隔离/多批次防重复/零库存测试，前端E2E，再执行获准本地首次同步并报告成功页数、记录数、未关联数、快照时间。测试通过不等于真实同步完成。

## 5. 当前需要补齐的材料

- storage/lists成功响应样本已收到并解析；当前为1条样本，不是全量6条，不执行部分数据覆盖发布。
- 用户在本地安全配置数据库与运行环境；若选择开放接口，再配置对应App凭据及来源账号，不在聊天中发送秘密。

## 6. 风险、回滚与结果

不修改生产库、.env、现有同步门禁或真实密钥；不部署，不提交推送。当前仅新增本文，无业务数据回滚。本任务尚未登录成功、抓取库存、写入本地库或填充看板，不能声称同步完成。

## 7. 已收到的网页响应结构与映射证据

用户随后提供成功响应，已用JSON解析校验。本文只记录字段结构，不复制真实商品、人员、图片地址或来源请求标识。

| 来源路径/字段 | 已确认事实 | 候选处理与限制 |
|---|---|---|
| code / msg | 样本code为1，msg为成功 | 与本系统success envelope不同；不能沿用开放接口code=0判断 |
| require_id | 来源追踪标识，拼写与request_id不同 | 独立保存来源追踪，不能伪造为本系统请求ID |
| data.list | 返回记录数组 | 样本1条，data.total声明6条；仅为结构样本，不能认为已同步6条 |
| data.current / data.size / data.total | 页码为整数，size为数字字符串，总数为整数 | 请求仍用offset/length；完整采集需验证翻页结果和总量，缺页/重复不能发布为完整快照 |
| wh_id / wh_name | 仓库字段名为wh_id，不是wid | ID规范为字符串，映射source_warehouse_id；不能复用开放接口字段名直接解析 |
| sku / product_id / product_name | 商品身份与名称 | product_id样本为整数，外部ID字符串化并保留原始来源类型 |
| store_id / store_id_list | 店铺相关字段，样本包含字符串0 | 0不能自动对应任何真实店铺；无确认归属时保持未知，不填默认店铺 |
| fnsku / msku及其数组 | 样本为空值/空数组 | 不生成ItemID/GTIN或Listing映射；本样本无ItemID、GTIN |
| hash_id | 来源提供数字字符串 | 保持字符串；尚无证据证明跨快照稳定，不能直接作为长期业务主键 |
| total / good_num / good_lock_num / bad_num / bad_lock_num / qc_num / transit_num | 样本为整数且均为0 | 原样保留0；数量字段的UI含义仍需对照，不自行计算可售量、在库量或净可用公式 |
| pending_num / expect_pending_num | 样本为数字字符串 | 标准化须显式校验整数，不将空字符串自动转0 |
| data.total_info | 样本值均为null或空字符串 | 本次请求has_statistic=false；无全局统计，不能拿单条或当前页替代 |
| bin_arr | 暂存/货位相关数组 | 不能当收货批次；样本各项是0也不代表全仓没有库存 |
| child_list / parent_field_array | 存在嵌套和归属字段 | 本样本child_list为空，不能据此假设所有请求均无子行或直接重复累计父子行 |
| principal_id_list / principal_name_list | 本样本无有效负责人 | permission_name_list不可直接映射当前产品负责人，仍使用已确认的产品负责人DWD |
| average_age / section1..8 | 库龄相关字段 | 没有日期和区间定义，不从平均库龄倒推出收货日期，不改到仓日期 |
| default_spec_pack | 来源默认箱规 | 可作后续箱规参考，不能当已经装箱或实际装箱记录 |

该库存样本不含receipt_order_sn、purchase_order_sn、batch_no、receive_time等批次追溯字段，不能单独生成现有收货批次表格。它能作为仓库/商品维度的库存补充来源；精确批次余额仍需明确关联证据。

安全展示候选：在收货批次详情中展示“同仓库同SKU的库存快照”，逐条显示来源维度与时间，并明确其不是本批库存。若表格未来展示此汇总，应限制重复累加；收货实收数量与库存总量分开。任何具体字段接入仍需正式PRP，本文不代替开发批准。

# 待发货打包单接口数据源决策

- 调查日期：2026-10-23。
- 调查人：后端工程师（兼顾本页面前端联调）。
- 接口总体状态：READY_FOR_PRP。
- 是否包含 NEED_OWNER_DECISION：否；来源可由现有新系统模型确定，新增业务规则以待确认 PRP 为准。
- 负责人批准状态：2026-10-23已确认本决策/PRP及本地新增结构、新记录范围，明确回复“确认，开发”；保留现有数据，不授权生产或外部执行。
- 目标前缀：候选 `/api/pmc/wfs/pending-packing`；本文件不是接口已存在的声明。
- 后续 PRP：`PRPs/pmc-wfs-pending-packing.md`，状态 APPROVED_FOR_IMPLEMENTATION。

## 1. 前置调查

| 调查项 | 证据与结论 |
|---|---|
| 旧页面 | 已于前轮读取 http://170.106.176.172:8088/wfs/；只作需求证据 |
| 旧 API | 旧代码 domestic/state、wfs/state、domestic/event、wfs/event；不作为新系统运行时数据源 |
| 旧接口文件 | `old-walmar-flie/features/pmc-replenishment/review_server/server.py`；旧 WFS `drafts/src/app-e.jsx` |
| 读取表 | 当前 PackingOrder、PackingBoxSet、PackingBoxLine、PackingVarianceCase 及既有治理后的 Listing/身份资料；未连接数据库核实实际部署 |
| 表写入方 | 国内仓审批/仓库 Service；未来 WFS Service 只拥有草稿、分配及自己的事件 |
| cron/脚本/外部 API | 本请求不执行；GET/POST 不触发领星、Walmart 或货代 |
| 人工写库入口 | 已有仓库 HTTP 命令；新草稿只经受权限保护的业务命令 |
| 外部平台重新获取 | 不能重建本系统 PK、实装、审批与占用事实；不适合作为来源 |
| 少量配置 | 退货地址可由本次提交输入并快照；不为页面重复建平台地址簿，不假装已有同步地址 |
| 短期策略 | 在当前本地连接中，以新系统事务事实构造查询读模型；不新建待发货事实表 |
| 长期策略 | 国内仓拥有装箱事实；WFS 拥有其草稿和装箱分配；外部执行另行批准 |

## 2. 数据集分类与权威

| 数据集 | 权威/分类 | 查询和写入边界 |
|---|---|---|
| PK、原审批数量、账号/仓库/店铺、身份快照、报关、版本 | `ops_domestic_packing_orders` / NEW_SYSTEM_OWNED | 查询和命令重新验证；不从旧系统兜底 |
| 实际装箱、尺寸、重量、完成时间、版本 | `ops_domestic_packing_box_sets`、`ops_domestic_packing_box_lines` / NEW_SYSTEM_OWNED | 只认本系统；改箱继续使用国内仓规则和审计 |
| 少装/多装、额外分配和阻塞 | 既有 variance_cases、allocations、extra_allocations / NEW_SYSTEM_OWNED | 不修改原 Q，不凭缺失证据判断零库存 |
| 可选择的目标店铺/Listing及商品身份 | 复用现有审批 identity/Listing 查询的已治理模型 / REBUILD_SYNC | 读取已发布新系统数据，不增加同步或实时外部请求；同账号同SKU，使用稳定ID |
| WFS 草稿、商品快照、装箱占用、提交审计 | 候选 `ops_pmc_wfs_drafts`、`ops_pmc_wfs_draft_items`、`ops_pmc_wfs_box_allocations`、`evt_pmc_wfs_draft_events` / NEW_SYSTEM_OWNED | 当前未实现；须 PRP 批准及独立结构授权；不冒用国内仓库存分配表 |
| 旧页面、旧 JSONL、旧执行器 | legacy_reference / ARCHIVE_ONLY | 仅需求与对账证据，不成为在线查询来源 |

不新增同步任务，不复制 ODS/RAW；本页面读模型是事务事实的有范围查询，不把读模型重新声明为权威来源。

## 3. 字段血缘和公式

| 字段组 | 来源/转换 | 标准及风险 |
|---|---|---|
| order_id/pk/approved_quantity | PackingOrder.id/pk/qty | UUID/字符串/整数；原审批数量保留 |
| source_account_ref/warehouse_id/store_id/item_id | PackingOrder及经验证目标身份 | 字符串ID；禁止店铺名称反查 |
| gtin/msku/title | 订单身份快照；换身份使用已发布有效Listing | GTIN字符串14位，缺失阻断建草稿；标题缺失不冒充外部已验证 |
| order_version/box_version | PackingOrder.version/BoxSet.version | 正整数；写命令必带预期值 |
| box_line_id/boxes/units_per_box | BoxLine.id/boxes/units_per_box | 整行分配；件数=箱数×每箱件数 |
| packed_quantity | 当前完成装箱行数量之和 | 使用真实 T，不能用 Q 代替；展示差异及来源 |
| remaining_quantity/boxes | 当前完成装箱减有效WFS分配 | 按行去重；占用草稿不能因失败或未知而静默释放 |
| test | 候选映射 PackingOrder.business_test | 与 is_test 环境保护分开；实施前以服务及测试确认语义，不改历史值 |
| completed_at/completed_by | BoxSet对应字段 | UTC存储，Asia/Taipei展示；不重写首次完成时间 |
| customs | PackingOrder.customs_value/customs_src | 显式修改写原因、登录人及不可变事件 |
| return_address/its | 草稿提交时校验输入并存快照 | 本系统用户输入，不宣称为平台验证地址/服务资格 |
| statistics/data_asof | 同一账号权限范围的查询聚合/查询时间及记录版本 | 响应记录统计筛选口径；无外部实时保证 |

刷新仅重新查询，GET 不执行写库。缺失装箱/身份分别返回阻断原因，不造数据补齐。

## 4. 本地连接与实施门禁

继续已有本地数据库连接，不读取回显秘密，不修改 .env。实际连接前核实 local 环境、获批 host/port/数据库身份，不能只根据127.0.0.1推断安全。此轮只做静态调查。

新增草稿结构、可能的国内仓事件类型扩展及权限定义应先列结构清单和回滚方案；不改已有 Alembic 历史、不擅自新增修订号或执行 SQL。本地结构授权独立于 Git 版本，后续正式发布仍遵守 Alembic only。既有库不灌样例、不清空、不更新已有业务记录来凑联调数据。

## 5. 确认清单

- [x] 数据集已逐项分类，旧资料仅作参考。
- [x] 来源和写入方具有仓库静态证据，数据库实际状态未核实。
- [x] 不实时访问外部平台、不默认双写、不直接查询RAW。
- [ ] 负责人确认数据源决策及PRP。
- [ ] 实施前确认本地结构及写入范围、核实身份与测试标记语义。
- [ ] 完成API字段字典、数据接口登记和真实测试。

# 国内仓：采购入库批次看板 API（M1）

状态：本地代码实现；生产0049迁移、惠州30天同步及版本发布已完成；未部署/重启生产服务。2026-10-20。

原 `/api/pmc/domestic/batches` 保留收货明细契约。以下是独立的入库单口径，国内仓批次页面已在dev接入；支持独立本地CSV核对模式。真实生产迁移/发布结果以执行记录为准。

## 来源与粒度

行 = 来源账号 × 仓库 × 采购入库单 × SKU × 批次店铺归属。仅惠州仓库经核实的来源 ID；配置采集目标时须先核对，代码不硬编码旧仓库 ID。

库存流水（新）`wareHouseCenterStatement` 的 2202 生成入库事实；`getBatchDetailList` 按入库单+SKU关联库存批次和当前余额。批次明细里的 22/2201/2202 采购来源可补窗口外行，但历史入库量保持未知。2401 调拨等不是采购入库来源。

当前模型读 `mart_domestic_inbound_batch_board` 和 `gov_domestic_board_publications`。GET 不访问领星、不读 RAW/ODS、不写库、不发 Celery 任务。真实采集目前默认仅文件模式；数据库发布另有显式授权入口。

## 权限

声明 `pmc:domestic-batch:read`，按现有请求策略映射 `page:pmc:domestic-warehouse-board:view`；复用可信 `source_account_ref` scope。无账号范围403；详情跨账号404。客户端筛选不能扩大服务器账号范围。登录凭证由前端请求封装携带，不写入URL。

## GET /api/pmc/domestic/inbound-batches

无请求体。参数：

| 参数 | 约束 |
|---|---|
| page / page_size | page≥1；page_size 1..200，默认50 |
| sort | inbound_date_desc 默认；inbound_date_asc；balance_desc；未知值422 |
| warehouse_id / store_id / sku / inbound_order_sn / purchase_order_sn | 重复参数数组，各最多50项；组内OR，组间AND；不接收owner_uid或ItemID过滤 |
| inbound_from / inbound_to | 业务日期范围；反序422 |
| inventory_status | known 或 unknown |
| search | 最多200字符，匹配入库单、SKU、采购单集合或批次号 |

未知参数422。空白ID拒绝；空日期/余额排末，追加稳定ID排序。

返回 envelope：`{success,data,error,meta,request_id}`；`data={items,total}`。

行字段：id、publication_id、source_account_ref、source_warehouse_id、warehouse_name、inbound_order_sn、sku、product_name、store_id、store_name、attribution_status、purchase_order_sns[]、draft_nos[]（按采购单号+SKU 读取采购看板 `dws_purchase_board.draft_no`，即采购备注中的草稿号；没有则为空数组，不新发号）、item_identities[]（item_id、gtin。按本行店铺、采购单号和 SKU 现算，不落新表。从采购明细 remark、payload 的 item_purchase_remark，以及关联计划的 remark、plan_remark、item_purchase_remark 取出全部独立 11 位，`ITEMID:` 优先，14 位 GTIN 不算。只保留这一行店铺的备注，且 Listing 的 local_sku 必须等于本行 SKU。对不上时用这一行店铺加 SKU 的 Listing。店铺为空时，仅当该 SKU 只在一个店铺上架才自动归属。一个号码为 resolved 并带上 Listing 的 GTIN，多个为 conflict，没有为 missing）、owner（uid、name、status。按账号+SKU 读取当前产品资料 `dwd_lingxing_sku_product_info_current`。一个有效身份且一个负责人 UID 时 status=resolved 并显示姓名；没有资料为 missing；多个身份或多个负责人 UID 为 conflict。不使用开发人、店铺负责人或入库创建人）、identity_status、inbound_at_raw、inbound_at、arrival_business_date、arrival_source、arrival_date_status、days_in_warehouse、total_inbound_qty、parent_inbound_qty、quantity_scope、balance_num、inventory_status、batch_nos[]、batch_details[]、history_complete、source_kind。

- `id` 为逻辑行稳定UUID，`publication_id` 为发布版本。每次请求固定版本；后续请求才看到新发布。
- `total_inbound_qty` 暂为null：没有直接店铺级分摊证据，不把父IB×SKU数量复制到各店铺行。
- `parent_inbound_qty` 是IB×SKU层级，跨店铺显示时不可直接相加；统计接口按父级去重。
- `quantity_scope=inbound_sku|unknown`；库存余额和历史入库量不同。
- `inventory_status=unknown` 的数量null；明确源余额0才显示0。库存0不等于已发货。
- `arrival_source=inventory_statement|batch_fallback|unknown`。源时区未确认，日期和天数保持null，不把文本当UTC。
- `days_in_warehouse` 按请求时Asia/Taipei日历日计算，和快照新鲜度分开。
- `history_complete=false`：窗口有限，不能据此声称全历史完整。
- `store_id=0/空` 显示null、归属unknown，不映射默认店铺。
- 不返回推算的发货完成率、打包状态、PK、ItemID、GTIN。

meta：source=new_system_postgresql；source_objects；data_status=not_published|ready；freshness_at；publication_ids[]；coverage_start/end（end不包含）；as_of；available_capabilities；page/page_size/total。

没有当前成功发布时：items=[]、total=0、data_status=not_published。成功的空发布也是items=[]，但data_status=ready并有发布ID。表结构未迁移不是“空发布”，服务端会返回统一错误，不伪装成功。

## GET /api/pmc/domestic/inbound-batches/summary

同业务筛选，不接收分页和sort。返回 board_row_count、inbound_order_count、sku_count、balance_qty、unknown_inventory_row_count、total_inbound_qty、unknown_inbound_qty_count、missing_arrival_date_count、as_of。

board_row_count是展示行数；inbound_order_count按账号/仓库/入库单去重；总入库量按父IB×SKU去重；余额按批次身份去重，仅已知值累计，未知条数另外返回。只筛某店铺时的父数量仍代表所匹配父IB×SKU的总量，不冒充该店铺历史分配量。

## GET /api/pmc/domestic/inbound-batches/{id}

返回同一行及批次组成。仅查询用户可见来源账号的当前发布；旧发布独有行不再当前可见时404。

## GET /api/pmc/domestic/inbound-batches/{id}/trace

data={batch,inbound_events,outbound_status,outbound_reason}。返回标准化入库事件（流水ID、单号、类型、数量、时间）和批次组成，不返回原始payload或鉴权数据。
outbound_status=unknown，outbound_reason=source_not_published；M1未实现出库分摊。

## 错误与文档

401 UNAUTHORIZED、403 FORBIDDEN/DATA_SCOPE_DENIED、404 NOT_FOUND、422 VALIDATION_ERROR、500 INTERNAL_ERROR。统一错误envelope不回显SQL/连接串。

FastAPI operationId/response_model 和数据中心API文档静态目录均登记这四条GET。采集和发布运行方式见 `docs/runbooks/pmc-domestic-inbound-csv.md`；操作说明见 `docs/sop/domestic-inbound-board-m1.md`。


实际数据验收：当前成功发布1441行（1362单、757个SKU），余额4392，父级已知入库量24787；历史量未知1200组，不能把已知量当成全历史总量。日期源时区已由负责人确认Asia/Shanghai，缺失日期0。库内mart2882行包括保留旧版，API只读当前版1441。CSV与当前版同源校验通过；登录态HTTP验证待本地旧后端重启生效。

## 2026-10-20 店铺与当前负责人选项衔接

`GET /api/pmc/domestic/inbound-batches/filter-options`，重复 warehouse_id 最多50项，不接受其他参数，无Body。返回统一 envelope，data={stores:[{value,label}],owners:[{value,label}],statuses:[{value,label,disabled,reason}],owner_basis:"current_product_owner"}。所有选项只来自可信账号和仓库内完整当前版本，不从当前50行生成。静态路径先于 /{inbound_id} 注册。

list/summary 共同支持重复 owner_uid 最多50项；字符串保留前导零，空白或过长422；同字段OR，店铺、负责人、日期等交集AND。当前产品负责人关联 account+SKU 且 active identity 唯一，缺失或多身份未知；EXISTS 避免复制数量。store_id 是ID而非店铺名。名称歧义用ID。

选项依赖 mart/gov、dim_lingxing_stores、dwd_lingxing_sku_identity_index、dwd_lingxing_sku_product_info_current；owner筛选的list/summary metadata增加两个负责人表。批次采集时间并不代表负责人维表同时间快照。权限、401/403/422/500、账号范围、request_id沿用既有入库接口；无审计业务写入、无队列、无外部调用。

六项状态为 in_stock/approved/packed/overdue/shipped/other_out；当前 disabled=true，reason说明尚无发布打包发货关联，不返回虚构状态数量。此期不接受 business_status 参数（422），后续方案批准并发布状态事实后再启用。

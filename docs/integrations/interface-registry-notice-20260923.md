# Interface Registry Notice — WFS / 物流探测结果登记（2026-09-23）

状态：`NOTICE`（登记与状态修正建议，不是开发授权、不是调用授权）
来源：业务流 AI 汇总的探测票据 registry_check / report（本地 `features/pmc-wfs-shipment/data/`、`features/pmc-domestic-warehouse/data/`、`features/pmc-logistics/`，均为部署 AI 按票据只读执行，除 §1.3 明确写出的一次已批准写测试）
提交：代码 AI（Rocky 转交，2026-09-23）
负责人决定：待 mz-liuyunlong

本文件只做四件事：登记新接口、给 `DO_NOT_USE` 行的复核证据与建议、记录已只读调用接口的登记状态、写清 WFS Receipt 口径与边界。**不新增任何生产调用，不新增写接口执行，不含凭证值，不含真实业务明细。**

---

## 0. 边界（全文适用）

1. 本 PR 不夹带功能开发，不触碰 `backend/`、`frontend/`、PMC Purchase 的任何 PR（#153 等）。
2. 本文件不改变任何 `DO_NOT_USE` 行的状态；改状态必须走 `docs/integrations/lingxing-walmart-openapi/do-not-use.md` §"允许重新评估的例外流程"，由负责人书面决定后另开 PR 修改 `API_CONTRACT_INVENTORY.csv` / `api-verification-status.csv`。
3. 凭证只记录存放路径（`secret_ref`），不记录、不复制、不打开任何值。
4. Walmart 写接口（§1.3 写 ×3）正式开发前必须重新审批；领星备货单装箱回写、产品箱规写入正式探测前必须审批（§4）。
5. 所有"已只读调用"均指部署 AI 按票据在服务器执行的只读拉取；产物不入 Git。

---

## 1. 需新增登记（登记表 / 外部接口登记里没有）

### 1.1 领星：查询 WFS 成本计价明细

| 项 | 值 |
|---|---|
| Endpoint | `POST /basicOpen/multiplatform/wfs/cost/valuation/detail` |
| 领星文档 | 2026-09-10 新增；仓库 329 条登记表（`docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv`）**无此行** |
| provider | lingxing |
| is_read / is_write / has_side_effect | 是 / 否 / 否 |
| token_bucket_capacity | 1 |
| 用途 | WFS 出入库流水（businessType：Receipt / Ship / Adjustment）+ 成本分摊；作为 Walmart `inventory-log` 的对账兜底 |
| 时间口径 | `dateLocal` = 美西时间（America/Los_Angeles） |
| 探测结论 | 票据 v8 已只读调用；逐条与 Walmart `inventory-log` 镜像对应 |
| 建议 classification | `READY_FOR_PRP`（只读、无副作用、已只读验证）；若负责人要求先走文档收录，则 `READ_ONLY_CANDIDATE` |
| 建议动作 | 追加到 `normalized/interfaces.csv` + `api-verification-status.csv` + `API_CONTRACT_INVENTORY.csv`（新 `LX-` id 按现有哈希规则生成），单独 PR |

### 1.2 众壹物流 API（外部系统，不属于领星登记表体系）

| 项 | 值 |
|---|---|
| 系统 | 众壹物流 TMS 开放接口（外部第三方） |
| 只读接口 | `POST /auth/getToken`（认证取 token，不是业务写入）、`GET /externalApi/baseProduct/listByCustomerNo`、`POST /externalApi/order/findOrderDetails`、`POST /externalApi/order/orderTrack`、`GET …/getSystemLabel` |
| 用途 | 物流轨迹 / 计费重 / 箱明细；无按日期列表接口，只能按运单号 / 客户单号查 |
| 凭证 `secret_ref` | `.secrets/logistics/6995/credentials.env`（仓库外；只记路径） |
| 登记位置 | `docs/data-registry/DATA_INTERFACE_REGISTRY.md` → External Interface Registry（本 PR 已加 `ext-zhongyi-logistics-readonly-candidate` 行，状态 `candidate`） |
| 边界 | 全部按只读登记；未纳入任何同步计划；正式接入需 Source Decision + PRP |

### 1.3 Walmart Marketplace API（外部系统）

只读 9 个（登记为 `candidate`，本 PR 已加 `ext-walmart-wfs-readonly-candidate` 行）：

| # | 接口 | 备注 |
|---|---|---|
| 1 | `POST /v3/token` | 认证取 token，不算业务写入 |
| 2 | `GET /v3/fulfillment/inbound-shipments` | 实测参数 `fromCreatedDate` / `toCreatedDate`，毫秒 UTC |
| 3 | `GET /v3/fulfillment/inbound-shipment-items` | |
| 4 | `GET /v3/fulfillment/inventory-log` | `gtin` 必传；WFS Receipt 流水主口径之一（§5） |
| 5 | `GET /v3/wfs/inventory` | |
| 6 | `GET /v3/items/{sku}` | |
| 7 | `GET /v3/fulfillment/inbound-shipment-errors` | |
| 8 | `GET /v3/fulfillment/inbound-shipments-tracking` | |
| 9 | `POST /v3/fulfillment/inbound-preview` | **POST 但为预览，不创建货件**；按只读 / no side effect 登记，特别标注 |

写 3 个（登记为 `blocked`（待审批），本 PR 已加 `ext-walmart-wfs-write-pending-approval` 行）：

| # | 接口 | 副作用 | 状态 |
|---|---|---|---|
| 1 | `POST /v3/fulfillment/inbound-shipments` | 创建货件 | **已授权测试过一次并已取消**（见下），不是正式开发授权 |
| 2 | `DELETE /v3/fulfillment/inbound-shipments/{inboundOrderId}` | 取消货件 | 同上 |
| 3 | `POST /v3/fulfillment/shipment-tracking` | 回填承运人 / 跟踪号 | 未测；正式开发前必须审批 |

已发生的写测试事实（记录，不是授权）：票据 v5 经 Rocky 批准，在店铺 HK2615 用接口 1 真实创建 1 张测试货件（客户单号 `<系统前缀>-TEST-20260922-01`（完整单号见本地票据 v5 报告，仓库不记））并用接口 2 取消，当前状态"已取消"。**正式开发前 Walmart 写接口必须重新走审批。**

凭证 `secret_ref` 规则：`.secrets/walmart/<领星store_id>/credentials.env`（仓库外；只记路径）。目前已落地两家店铺：HK2614、HK2615。

---

## 2. `DO_NOT_USE` 但疑似只读查询的接口 — 核对证据与建议

核对方法：`docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv`（is_read / is_write / has_side_effect 标记）、`API_CONTRACT_INVENTORY.csv`（contract_status）、`api-verification-status.csv`、本地探测报告。本文件**不改任何状态**。

### 2.1 `LX-C99E2D00C76D` `POST /cepf/warehouse/api/openApi/queryShippingListPage`（查询平台仓发货单列表）

| 核对项 | 结果 |
|---|---|
| 当前登记 | `API_CONTRACT_INVENTORY.csv`: `DO_NOT_USE` / `reference_only`；`interfaces.csv`: **`is_read=否 / is_write=是 / has_side_effect=是`** |
| 文档语义 | `interfaces.csv.purpose`："该接口仅支持 walmart，现已提供 v2 接口……平台仓发货单列表数据"；`pagination_method=offset/length`；接口名与文档标题均为"查询…列表"。仓库无该文档的 legacy Markdown 快照（`notes: no matching repository legacy Markdown snapshot`），所以 `is_write=是` 没有文档依据，判断为**标记录入错误**（同一批"查询平台仓发货单列表v2 / 详情"两行也被标成写，见 2.3/2.4） |
| 探测记录 | 国内仓票据 v2（2026-09-17，`features/pmc-domestic-warehouse/data/probe_20260917_v2/report_v2.md`）：只读调用成功，12 个月 503 张发货单；WFS 票据 v4（2026-09-22，`features/pmc-wfs-shipment/data/probe_lingxing_wfs_allstores_20260922/report.md`）：只读调用成功，530 张；报告 §88 已明确记录此登记冲突。两次调用均为列表查询，未发起任何创建 / 更新 / 取消 / 发货 / 拣货请求 |
| 副作用 | 未发现；调用前后领星侧数据无变化的证据以探测报告为准（报告只做 GET 语义的 POST 查询） |
| 依赖 | 物流看板全部 SP 发货单数据依赖它（`features/pmc-logistics/`） |
| **建议** | 走 do-not-use.md 例外流程：负责人批准 → 把 `interfaces.csv` 该行改为 `is_read=是 / is_write=否 / has_side_effect=否`，`API_CONTRACT_INVENTORY.csv` 改 `READY_FOR_PRP` / `candidate_source_read` / `AUTH_UNKNOWN`，`api-verification-status.csv` 记录两次只读验证日期与票据。物流板块 Source Decision 引用它 |

### 2.2 `LX-4B9473A2D2E1` `POST /erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/getOrderList`（查询收货单列表）

| 核对项 | 结果 |
|---|---|
| 当前登记 | **已不是 `DO_NOT_USE`**：PR #126（`ed4ff26`，2026-09-19）按负责人 2026-09-18 决定改为 `READY_FOR_PRP` / `source_candidate` / P0，风险保留 `AUTH_UNKNOWN`；`interfaces.csv` 本来就是 `is_read=是 / is_write=否 / has_side_effect=否` |
| 只读证据 | 采购 PR-F 生产首窗（2026-09-22）已按 runbook 只读拉取 543 单头 / 576 明细，无写入 |
| **建议** | 通知中的"DO_NOT_USE"是旧信息，无需再动；可在 `api-verification-status.csv` 补 `tested_status=已只读验证（2026-09-22，PR-F）` |

### 2.3 `LX-9D5A176AC470` `POST /basicOpen/multiplatform/query/shippingList`（平台仓发货单列表 v2）

| 核对项 | 结果 |
|---|---|
| 当前登记 | `DO_NOT_USE`；`interfaces.csv`: `is_read=否 / is_write=是 / has_side_effect=是`，`pagination_method=offset/length` |
| 文档语义 | purpose："原接口仅支持 walmart，现已提供 v2 接口，支持多平台……列表数据"——查询列表 |
| 调用 | 国内仓 v2 探测调用返回 400（参数有误），**未成功、未再调用**；只是 2.1 的备选 |
| **建议** | 与 2.1 同一批标记错误；状态核对结论"疑标错、未验证"。**不主动调用**；若负责人批准复评，与 2.1 一起改标记，但 `contract_status` 保持 `NEED_OWNER_DECISION`/`PARTIAL_CONTRACT` 直到有一次只读验证 |

### 2.4 `LX-418571887440` `POST /basicOpen/multiplatform/query/shippingDetail`（平台仓发货单详情）

| 核对项 | 结果 |
|---|---|
| 当前登记 | `DO_NOT_USE`；`interfaces.csv`: `is_read=否 / is_write=是 / has_side_effect=是` |
| 文档语义 | purpose："查询平台仓发货单详情" |
| 调用 | 国内仓 v2 探测返回 500，放弃；**未再调用** |
| **建议** | 同 2.3：只核对，不调用；标记疑错，等负责人复评 |

---

## 3. 已登记 `READY_FOR_PRP`、已只读调用（仅记录，无需动作）

| Interface | Endpoint | 登记 | 只读调用 |
|---|---|---|---|
| `LX-725F26FDC523` 查询物流-头程物流商 | `/basicOpen/logistics/headLogisticsProvider/query/list` | `READY_FOR_PRP` / read | WFS 票据 v4（返回 0 条） |
| `LX-E95A3442D310` 查询头程物流渠道列表 | `/erp/sc/data/local_inventory/channelList` | `READY_FOR_PRP` / read | WFS 票据 v4（61 条） |
| `LX-531E7CE81EF4` 查询WFS库存列表 | `/cepf/warehouse/api/openApi/queryWFSInventionPage` | `READY_FOR_PRP` / read / P0 | 已只读调用 |

### 3.1 报告未写明登记状态的 4 个接口 — 已核对 registry

| Interface | Endpoint | 登记（`API_CONTRACT_INVENTORY.csv` / `interfaces.csv`） | 结论 |
|---|---|---|---|
| `LX-C95DBD64F2A9` 查询WFS货件列表 | `POST /cepf/warehouse/api/openApi/queryWFSCargoPage` | `READY_FOR_PRP` / `candidate_source_read` / P1；read=是 write=否 | 状态正确；已只读调用（979 张） |
| `LX-7773B7A1FDF9` 查询海外仓备货单列表 | `POST /erp/sc/routing/owms/inbound/listInbound` | `READY_FOR_PRP` / P0；read=是 write=否 | 状态正确；已只读调用 |
| `LX-EB2B3813F515` 查询备货单详情 | `POST /basicOpen/overSeaWarehouse/stockOrder/detail` | `READY_FOR_PRP` / P0；read=是 write=否 | 状态正确；已只读调用 |
| `LX-E5E2F516B966` 查询备货单装箱信息 | `GET /erp/sc/routing/owms/inbound/getPackingData` | `READY_FOR_PRP` / P0；read=是 write=否 | 状态正确；已只读调用 |

四条均无需改状态；建议后续在 `api-verification-status.csv` 补 `tested_status=已只读验证` 与票据日期（单独 PR，不在本文件）。**不扩大调用范围。**

---

## 4. 写接口结论（记录，不登记为可用）

### 4.1 领星 Walmart 平台仓 SP 发货单：无字段更新接口

领星 v7 文档核对：只有 FBA 的三个 `update*` 接口，且这三个已 `DELETED`（见 `normalized/deleted_interfaces.csv`）；平台仓只有 delivery / picking 状态接口。**结论：用物流商轨迹反向写入领星四个时间目前没有通道。** 不得写成"已可落地"，不得设计为现在就能回写领星；路线由 Rocky 另定。

### 4.2 领星备货单装箱回写、产品箱规写入：待探测 / 待审批

- 备货单装箱回写（国内仓"修正装箱"）：目标接口未定，**正式探测前必须审批**。
- 产品箱规写入：候选 `LX-F00018116434 POST /erp/sc/routing/storage/product/set`（添加/编辑本地产品，`spec_pack_list`），登记 `DO_NOT_USE` / write=是。**正式探测前必须审批**，本通知不申请。

### 4.3 国内仓 `LX-5567B5700B78 POST /erp/sc/routing/owms/inbound/createInbound`

W1 测试（2026-09-17，Rocky 一次性例外批准）返回 `code=500`，**探测失败、未产生单据、未产生副作用、未创建成功**。后续 W5 成功建单并已在 W5C 删除（见 `features/pmc-domestic-warehouse/context/test-w5-findings.md`）。登记状态保持 `DO_NOT_USE`；不把 W1 当作已创建单据。

---

## 5. WFS 口径变更：三个关键状态统一改为 Receipt 流水口径

| 项 | 口径 |
|---|---|
| 三个状态 | 开始收货 / 收货完成 / 可售 |
| 主数据源 | Walmart `GET /v3/fulfillment/inventory-log` |
| 粒度 | 货件级（shipmentId） |
| 时间 | UTC |
| 拉取键 | 按 GTIN |
| 判定 | 用 Receipt 类型流水判断"开始收货"（首条 Receipt）、"收货完成"（Receipt 累计达货件数量 / 货件关闭）、"可售"相关状态；具体阈值由 WFS 货件板块业务规则定 |
| 对账兜底 | 领星 `POST /basicOpen/multiplatform/wfs/cost/valuation/detail`（§1.1；`dateLocal` 美西时间，对账时统一换成 UTC） |
| 滞后规则 | **若领星货件状态仍为 AWAITING，但 Walmart inventory-log 已有 Receipt 流水，一律按"收货中"处理。** 探测已证明领星货件状态滞后，不得单独依赖领星货件状态判断 WFS 是否开始收货 |

---

## 6. 后续 PR 建议（按顺序，各自独立）

1. **docs/registry**：负责人批准后，`LX-C99E2D00C76D`（及 2.3 / 2.4 同批标记）从 `DO_NOT_USE` 改为只读查询状态；`api-verification-status.csv` 补只读验证记录（含 3.1 四条与 2.2）。
2. **docs/registry**：新增 `LX-` 行登记 §1.1 领星 WFS 成本计价明细。
3. **docs/source-decision**：物流板块 Source Decision（队列 `queryShippingListPage` + 众壹物流 + Walmart 只读）；WFS 货件板块 Source Decision（Walmart 只读 9 + 领星兜底）。
4. **PRP**：WFS 货件板块 Gate 1（只读同步），Walmart 写接口留作独立 Gate，开发前重新审批。
5. **不做**：任何生产调用、任何写接口执行、任何凭证值输出。

---

## 7. 本通知对应的登记表改动（本 PR）

仅 `docs/data-registry/DATA_INTERFACE_REGISTRY.md` External Interface Registry 新增 4 行（状态 `candidate` / `blocked`），不改任何既有行：

- `ext-lingxing-wfs-cost-valuation-detail-candidate`
- `ext-zhongyi-logistics-readonly-candidate`
- `ext-walmart-wfs-readonly-candidate`
- `ext-walmart-wfs-write-pending-approval`

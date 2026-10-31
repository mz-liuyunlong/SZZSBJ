# Listing 管理监控 RAW 字段盘点（LM-071）

状态：本地监控端实际数据及当前代码已盘点；生产接收端覆盖率尚未验收。

## 范围与证据

- 只读扫描桌面监控程序当前运行库中 `checks.result_json` 的 JSON 键名与类型；没有读取或输出字段值、商品标识或原始文件。
- 对照监控端 `lib/integrations/outbox.ts::parsedMonitorResult`、`lib/types.ts::SuccessfulScrape`，以及本仓库 `backend/app/modules/walmart_monitor/schemas.py`、`projection.py`。
- 本地另一个旧 `data/monitor.db` 不含 `checks.result_json`，不能用作当前 RAW 字段样本。
- `checks.result_json` 是监控端的历史解析结果；真正投递到新系统的完整事件还包含 `producer`、`targets[]`、`attempts[]` 和 `final_observation`。两种采集模式共用 `walmart-monitor.raw.v1`，不拆成两张 RAW 表。
- 本盘点不证明生产 `raw_walmart_monitor_events` 已收到所有历史事件，也不证明所有字段完整、准确或有业务权威。

## 当前解析结果的顶层键

以下是实际扫描出现的全部 30 个顶层键。没有出现的键不代表协议禁止；监控端可从 `checks` 的结构化列补成投递结果，接收端也允许 `parsed_result` 扩展键。

| 来源键 | 当前去向 | 边界 |
|---|---|---|
| `productTitle` | L3 `title` → L9 标题 → Listing 页面 | 仅成功观察的非空值；否则回退 Listing |
| `strikethroughPriceCents` | L3/L9 划线价金额 | 与 `currency` 成组；不猜币种 |
| `currentPrice` | L3/L9 在售价金额 | 与 `currency` 成组；不猜币种 |
| `currency` | L3/L9 上述金额的币种 | 不做未经授权的换汇 |
| `cartStatus` | L3/L9 购物车状态 | 不等于明确跟卖结论 |
| `sellerName` | L3/L9 Walmart 卖家 | 仅展示观察值 |
| `ratingSummary` | `rating`、`reviewCount` 标准化后进入 L3/L9 | `reviewFetchStatus` 留在 RAW，不等于评分值 |
| `productBrand` | L3/L9 页面品牌 | 不凭品牌字符串自动判定文案异常 |
| `productImageUrls` | L3/L9 HTTPS 图片列表 | 运营页只展示安全 URL，失败时回退旧图 |
| `walmartCategory` | `path[*].name` 形成 L3/L9 页面类目 | `categoryPathId`、`source` 保留 RAW；与 `targets[].product_category` 不同 |
| `kind`, `checkedAt`, `durationMs`, `dataSource` | RAW/审计 | 业务采集时间及状态以事件外层已校验字段为准 |
| `hasStrikethrough`, `strikethroughSource`, `cartDiagnostics` | RAW/审计 | 不以布尔值替代金额或正式异常状态 |
| `sellerSource`, `sellerNames`, `otherSellersPresent`, `sellerOfferCount` | RAW/审计 | 仅卖家出现不能推出外部跟卖；不能直接发布到业务页 |
| `keyFeatures`, `productImageCount` | RAW/审计 | 不作为标题、图片列表或文案风险的权威来源 |
| `diagnostic`, `rawPayloads` | 受限 RAW/审计 | 可能含页面、位置或抓取诊断；不得进入 Listing API、普通日志或公开文档 |
| `code`, `message`, `originalItemId`, `candidateItemId`, `evidenceUrl` | 受限 RAW/错误诊断 | 失败与身份疑点证据；不得自动改稳定业务键或在页面暴露原文 |

监控端投递时还可能根据 `checks.reseller_status` 补出 `resellerStatus` 与 `isHijacked`；这两个键没有出现在本次 `checks.result_json` 顶层扫描中。接收端只接受明确布尔值或已识别的跟卖状态，缺失时保持未知。`strikethroughPrice`、`rating`、`reviewCount` 是接收端兼容的候选键，本次样本没有出现；不可因为解析器支持就声称历史已覆盖。

已观察到的嵌套键：`ratingSummary` 含 `rating`、`reviewCount`、`reviewFetchStatus`；`walmartCategory` 含 `categoryPathId`、`path`、`source`；`cartDiagnostics` 与 `diagnostic` 均只留作审计，不进入当前 Listing 字段。原始压缩来源位于事件 `attempts[].source_payloads[]`，不通过前端读取。

## 生产前剩余核对

1. 由获授权人员在生产接收库以只读事务统计事件数、版本、成功/失败和键覆盖率；只输出聚合，不输出 payload、身份或商品明细。
2. 对未知键先进行受限审计和字段标准化决策；不能直接从 RAW 添加到 Listing API。
3. 比对监控端已成功投递事件与接收端幂等事件数量，确认历史回传是否完整；本地 `checks` 数量不能代替接收确认。
4. 类目、品牌和跟卖误报需用获批脱敏样本验证，不能仅凭键存在判为准确。

本文件只盘点来源字段，不修改 RAW、L3、L9、Listing 页面、同步任务或权限。

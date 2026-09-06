# Phase 1 候选接口清单

本文件基于 `normalized/module_mapping.csv` 的 `phase_one_recommended=是` 自动整理。

> 重要：这里的“候选”不是“允许直接开发”。所有接口接入前必须单独 PRP、真实验证、确认账号权限和返回字段。

## 汇总

- 候选映射行：163
- 去重候选接口：103

| 新系统模块 | 候选映射行 |
|---|---:|
| 销售 | 43 |
| 仓库 | 40 |
| 运营 | 28 |
| 产品 | 21 |
| 财务 | 10 |
| 售后 | 7 |
| 采购 | 7 |
| Walmart | 5 |
| 工作台 | 2 |

## 使用原则

1. 优先选择只读查询接口。
2. 优先选择能替代旧库同步来源的接口，而不是替代已经算好的 FACT/BIZ 结果表。
3. 写入类接口、批量修改、上传、删除、价格修改、Listing 变更、仓库/采购写入类接口默认不进第一期。
4. 广告、SEM、否定关键词等如果文档或旧系统证据不足，先继续读旧库/人工日志，不要强行接 API。
5. 候选接口必须先在 `api-verification-status.csv` 标记实测状态，再进入 PRP。

## 模块候选接口概览

### Walmart

| 页面 | 接口ID | 接口名 | 方法 | 路径 | 说明 |
|---|---|---|---|---|---|
| Walmart 业务中心 | `LX-727003CFF7B4` | Walmart-查询结算账单列表 | POST | `/basicOpen/multiplatformFinance/walmart/bill/statement/list` | Walmart-查询结算账单列表，支持按订单、商品、账期、交易类型、金额类型和时间范围查询 Walmart 结算账单明细。 |
| Walmart 业务中心 | `LX-63E99B54ED72` | Walmart-查询回款明细列表 | POST | `/basicOpen/multiplatformFinance/walmart/bill/payout/list` | Walmart-查询回款明细列表，支持按店铺、站点、账期、时间和金额比较条件查询 Walmart 回款明细。 |
| Walmart 业务中心 | `LX-1524E1C3FF10` | 查询Walmart产品表现 | POST | `/basicOpen/platformStatistics/walmartProductAnalysis/list` | 查询Walmart产品表现列表数据，对应系统【统计分析】>【多平台产品表现】>【Walmart】数据 |
| Walmart 业务中心 | `LX-571E669C2E50` | 多平台-Walmart售后订单列表 | POST | `/basicOpen/openapi/multiplatform/walmart/returnOrder/list` | 多平台-Walmart售后订单列表 |
| Walmart 业务中心 | `LX-9212623D77EA` | 查询Walmart在线商品 | POST | `/basicOpen/multiplatform/walmart/list` | 查询Walmart在线商品 |

### 产品

| 页面 | 接口ID | 接口名 | 方法 | 路径 | 说明 |
|---|---|---|---|---|---|
| 产品管理页 | `LX-C76D747AD0DA` | 刊登管理-获取指定 productType 的 JSON Schema | POST | `/basicOpen/openapi/publish/manage/getProductType` | 刊登管理-获取指定 productType 的 JSON Schema |
| 产品管理页 | `LX-44D4A6C312C6` | 获取UPC编码列表 | POST | `/listing/publish/api/upc/upcList` | 获取UPC编码列表 |
| 产品管理页 | `LX-3F1F087FF8A1` | 查询本地产品列表 | POST | `/erp/sc/routing/data/local_inventory/productList` | 支持查询产品列表，对应系统【产品】>【产品管理】数据 |
| 产品管理页 | `LX-DCB0C142100B` | 查询本地产品详情 | POST | `/erp/sc/routing/data/local_inventory/productInfo` | 支持查询本地产品详细信息，对应系统【产品】>【产品管理】数据 |
| 产品管理页 | `LX-BB8D0DF598AF` | 批量查询本地产品详情 | POST | `/erp/sc/routing/data/local_inventory/batchGetProductInfo` | 批量查询本地产品详情 |
| 产品管理页 | `LX-A4D3F436FF1F` | 查询产品属性列表 | POST | `/erp/sc/routing/storage/attribute/attributeList` | 查询产品属性列表 |
| 产品管理页 | `LX-5AFC6979F657` | 查询多属性产品列表 | POST | `/erp/sc/routing/storage/spu/spuList` | 查询多属性产品列表 |
| 产品管理页 | `LX-30AF347E45FE` | 查询多属性产品详情 | POST | `/erp/sc/routing/storage/spu/info` | 查询多属性产品详情 |
| 产品管理页 | `LX-DA189364D1B7` | 查询捆绑产品关系列表 | POST | `/erp/sc/routing/data/local_inventory/bundledProductList` | 查询捆绑产品关系列表 |
| 产品管理页 | `LX-BD16C6D25A0D` | 查询产品辅料列表 | POST | `/erp/sc/routing/data/local_inventory/productAuxList` | 查询产品辅料列表 |
| 产品管理页 | `LX-82FF3AF996D2` | 查询产品品牌列表 | POST | `/erp/sc/data/local_inventory/brand` | 支持查询本地产品品牌列表，对应系统【产品】>【品牌管理】数据 |
| 产品管理页 | `LX-75F4963569A6` | 查询产品分类列表 | POST | `/erp/sc/routing/data/local_inventory/category` | 支持查询本地产品的分类列表，对应【产品】>【产品分类】数据 |
| 产品管理页 | `LX-226730376E6B` | 查询产品标签 | GET | `/label/operation/v1/label/product/list` | 查询产品标签 |
| 产品管理页 | `LX-6F96FE519F29` | 查询操作日志 | POST | `/basicOpen/product/getPagingLogLists` | 查询操作日志 |
| 产品管理页 | `LX-F6A548F96FD0` | 产品管理-查询透明计划商品列表 | POST | `/basicOpen/product/getTransparencyProductList` | 产品管理-查询透明计划商品列表 |
| 产品管理页 | `LX-CF87F80AD608` | 查询产品仓位列表 | POST | `/basicOpen/warehouseConfig/warehouseBin/getEntryRecommendBinList` | 查询产品仓位列表 |
| 产品管理页 | `LX-814E67414272` | 查询系统产品与第三方海外仓产品映射列表 | POST | `/erp/sc/routing/owms/inbound/matchSkuList` | 支持查询本地产品与第三方海外仓产品映射列表 |
| 产品管理页 | `LX-AAFAE3E2B6D6` | 获取第三方SKU标签PDF文件 | POST | `/erp/sc/routing/owms/inbound/productLabel` | 支持获取谷仓、西邮智仓、易仓的第三方SKU标签PDF文件 |
| 产品管理页 | `LX-09FE9E838C58` | 查询订单利润-MSKU | POST | `/basicOpen/finance/mreport/OrderProfit` | 唯一键说明：sid+msku |
| 产品管理页 | `LX-95A42DA552D3` | 查询采购报表列表 - 产品 | POST | `/basicOpen/report/purchase/product/list` | 查询采购报表列表 - 产品 |
| 产品管理页 | `LX-1524E1C3FF10` | 查询Walmart产品表现 | POST | `/basicOpen/platformStatistics/walmartProductAnalysis/list` | 查询Walmart产品表现列表数据，对应系统【统计分析】>【多平台产品表现】>【Walmart】数据 |

### 仓库

| 页面 | 接口ID | 接口名 | 方法 | 路径 | 说明 |
|---|---|---|---|---|---|
| 仓库与库存页 | `LX-96F32A1090F0` | 查询加工计划列表 | POST | `/basicOpen/openapi/workOrder/processPlanList` | 支持查询加工计划列表，对应系统【采购】加工计划列表数据。 |
| 仓库与库存页 | `LX-41E509578C0D` | 查询仓库列表 | POST | `/erp/sc/data/local_inventory/warehouse` | 支持查询本地仓库列表信息，对应系统【设置】>【仓库设置】仓库列表 |
| 仓库与库存页 | `LX-EC6F4C39346F` | 查询本地仓位列表 | POST | `/erp/sc/routing/data/local_inventory/warehouseBin` | 查询本地仓位列表 |
| 仓库与库存页 | `LX-CF87F80AD608` | 查询产品仓位列表 | POST | `/basicOpen/warehouseConfig/warehouseBin/getEntryRecommendBinList` | 查询产品仓位列表 |
| 仓库与库存页 | `LX-A791179C9A78` | 查询AWD库存列表 | POST | `/basicOpen/openapi/storage/awdWarehouseDetail` | 查询AWD库存列表 |
| 仓库与库存页 | `LX-41B3AF612B29` | 查询仓库库存明细 | POST | `/erp/sc/routing/data/local_inventory/inventoryDetails` | 支持查询本地仓/海外仓库存明细，对应系统【仓库】>【库存明细】数据 |
| 仓库与库存页 | `LX-47310BFA3E0D` | 查询仓位库存明细 | POST | `/erp/sc/routing/data/local_inventory/inventoryBinDetails` | 查询仓位库存明细 |
| 仓库与库存页 | `LX-1181D4F827FB` | 查询批次明细 | POST | `/erp/sc/routing/data/local_inventory/getBatchDetailList` | 查询批次明细 |
| 仓库与库存页 | `LX-BCB9BCE2437F` | 查询批次流水 | POST | `/erp/sc/routing/data/local_inventory/getBatchStatementList` | 查询批次流水 |
| 仓库与库存页 | `LX-F0CE5B7F589B` | 查询库存流水（新） | POST | `/erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement` | 查询库存流水（新） |
| 仓库与库存页 | `LX-8DE4E360B561` | 查询仓位流水 | POST | `/erp/sc/routing/data/local_inventory/wareHouseBinStatement` | 查询仓位流水 |
| 仓库与库存页 | `LX-4B9473A2D2E1` | 查询收货单列表 | POST | `/erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/getOrderList` | 查询收货单列表 |
| 仓库与库存页 | `LX-1C62776E886A` | 查询销售退货单列表 | POST | `/pb/mp/returns/v2/list` | 查询销售退货单列表 |
| 仓库与库存页 | `LX-ECAEE8038F87` | 查询质检单列表 | POST | `/erp/sc/routing/deliveryReceipt/ReceiptOrderQc/getOrderList` | 查询质检单列表 |
| 仓库与库存页 | `LX-5D311ED3B89E` | 查询质检单详情 | POST | `/basicOpen/qualityInspectionOrder/detail` | 查询质检单详情 |
| 仓库与库存页 | `LX-A78D6BB9DC24` | 查询入库单列表 | POST | `/erp/sc/routing/storage/inbound/getOrders` | 查询入库单列表 |
| 仓库与库存页 | `LX-179D3B8A9F63` | 查询出库单列表 | POST | `/erp/sc/routing/storage/outbound/getOrders` | 查询出库单列表 |
| 仓库与库存页 | `LX-F23293A702BB` | 查询销售出库单详情 | POST | `/basicOpen/wmsOrder/getWmsOrdersByOrderNumbers` | 支持查询ERP中【仓库】>【销售出库单】数据，即自发货订单销售出库单 |
| 仓库与库存页 | `LX-29AE97DABE08` | 加工单列表 | POST | `/erp/sc/routing/inventoryReceipt/StorageProcess/getOrderLists` | 加工单列表 |
| 仓库与库存页 | `LX-4E3A3DA2B70A` | 查询调拨单列表 | POST | `/erp/sc/routing/inventoryReceipt/StorageAllocation/getStorageAllocationList` | 支持查询本地仓库调拨单列表 |
| 仓库与库存页 | `LX-9909117FD1E7` | 查询调整单列表 | POST | `/erp/sc/routing/inventoryReceipt/StorageAdjustment/getStorageAdjustOrderList` | 查询调整单列表 |
| 仓库与库存页 | `LX-D5353A465E6D` | 查询盘点单列表 | POST | `/erp/sc/routing/inventoryReceipt/InventoryCheck/getOrderList` | 查询盘点单列表 |
| 仓库与库存页 | `LX-642D33967219` | 查询盘点单详情 | POST | `/erp/sc/routing/inventoryReceipt/InventoryCheck/getOrderDetail` | 查询盘点单详情 |
| 仓库与库存页 | `LX-75157159D29E` | 获取自定义入库类型 | POST | `/erp/sc/routing/storage/inbound/getCustomTypes` | 获取自定义入库类型 |
| 仓库与库存页 | `LX-10C1BC0E9648` | 获取自定义出库类型 | POST | `/erp/sc/routing/storage/outbound/getCustomTypes` | 获取自定义出库类型 |
| ... | ... | ... | ... | ... | 还有 15 行，完整见 `phase-1-candidate-apis.csv` |

### 售后

| 页面 | 接口ID | 接口名 | 方法 | 路径 | 说明 |
|---|---|---|---|---|---|
| 售后与客服页 | `LX-853A6501F0BF` | 查询采购退货单列表 | POST | `/erp/sc/routing/purchase/purchase_return_order/getPurchaseReturnOrderList` | 查询采购退货单列表 |
| 售后与客服页 | `LX-1C62776E886A` | 查询销售退货单列表 | POST | `/pb/mp/returns/v2/list` | 查询销售退货单列表 |
| 售后与客服页 | `LX-5470F505D06E` | 查询售后工单列表 | POST | `/pb/mp/returns/workOrder/list` | 查询售后工单列表 |
| 售后与客服页 | `LX-EA8918986608` | 查询店铺绩效列表 | POST | `/basicOpen/customerService/storeTarget/list` | 查询店铺绩效列表 |
| 售后与客服页 | `LX-54F0AD822356` | 查询店铺绩效详情 | POST | `/basicOpen/customerService/storeTarget/detail` | 查询店铺绩效详情 |
| 售后与客服页 | `LX-B5184BA8522B` | 统计-查询退货分析 | POST | `/basicOpen/salesAnalysis/returnOrder/analysisLists` | 支持统计-查询退货分析 |
| 售后与客服页 | `LX-571E669C2E50` | 多平台-Walmart售后订单列表 | POST | `/basicOpen/openapi/multiplatform/walmart/returnOrder/list` | 多平台-Walmart售后订单列表 |

### 工作台

| 页面 | 接口ID | 接口名 | 方法 | 路径 | 说明 |
|---|---|---|---|---|---|
| 数据总览 / 待评估接口 | `LX-F8354824E040` | 查询多平台店铺信息 | POST | `/pb/mp/shop/v2/getSellerList` | 支持查询多平台店铺基础信息，其中store_id为多平台店铺唯一 |
| 数据总览 / 待评估接口 | `LX-531E7CE81EF4` | 查询WFS库存列表 | POST | `/cepf/warehouse/api/openApi/queryWFSInventionPage` | 查询WFS库存列表 |

### 财务

| 页面 | 接口ID | 接口名 | 方法 | 路径 | 说明 |
|---|---|---|---|---|---|
| 财务与对账页 | `LX-E67765C12B1D` | 查询利润报表-店铺 | POST | `/bd/profit/report/open/report/seller/list` | 查询利润报表-店铺 |
| 财务与对账页 | `LX-69B7BDB30BF3` | 查询利润报表-店铺月度汇总 | POST | `/bd/profit/report/open/report/seller/summary/list` | 查询利润报表-店铺月度汇总 |
| 财务与对账页 | `LX-27FD5B4A5146` | 查询利润报表 - 订单维度transaction视图 | POST | `/basicOpen/finance/profitReport/order/transcation/list` | 查询利润报表 - 订单维度transaction视图 |
| 财务与对账页 | `LX-F30C3A5673B7` | 查询利润报表-订单 | POST | `/bd/profit/report/open/report/order/list` | 本接口即将下线【不再建议使用】，建议使用[查询利润报表 - 订单维度transaction视图](/docs/Finance/profitReportOrderTranscationList) |
| 财务与对账页 | `LX-598C49EB1197` | 查询请款单列表 | POST | `/basicOpen/finance/requestFunds/order/list` | 查询请款单列表 |
| 财务与对账页 | `LX-A5F6A7E6639A` | 查询利润统计-店铺 | POST | `/bd/profit/statistics/open/seller/list` | 支持查询新版利润统计的店铺维度 |
| 财务与对账页 | `LX-09FE9E838C58` | 查询订单利润-MSKU | POST | `/basicOpen/finance/mreport/OrderProfit` | 唯一键说明：sid+msku |
| 财务与对账页 | `LX-727003CFF7B4` | Walmart-查询结算账单列表 | POST | `/basicOpen/multiplatformFinance/walmart/bill/statement/list` | Walmart-查询结算账单列表，支持按订单、商品、账期、交易类型、金额类型和时间范围查询 Walmart 结算账单明细。 |
| 财务与对账页 | `LX-63E99B54ED72` | Walmart-查询回款明细列表 | POST | `/basicOpen/multiplatformFinance/walmart/bill/payout/list` | Walmart-查询回款明细列表，支持按店铺、站点、账期、时间和金额比较条件查询 Walmart 回款明细。 |
| 财务与对账页 | `LX-DB6D62E9EE37` | 查询结算利润（利润报表）-订单 | POST | `/basicOpen/multiplatform/profit/report/order` | 查询结算利润（利润报表）-订单 |

### 运营

| 页面 | 接口ID | 接口名 | 方法 | 路径 | 说明 |
|---|---|---|---|---|---|
| 运营分析页 | `LX-71422945ADAC` | 查询Listing标签列表 | POST | `/basicOpen/globalTag/listing/page/list` | 查询Listing标签列表 |
| 运营分析页 | `LX-EB69D6DC93FB` | 查询Listing操作日志列表 | POST | `/basicOpen/listingManage/listingOperateLog/pageList` | 查询Listing操作日志列表 |
| 运营分析页 | `LX-F560D3DA6DF1` | 查询优惠券详情+listing+订单(批量) | POST | `/promotionApi/open/promotion/couponAllDetailBatch` | 查询优惠券详情+listing+订单(批量) |
| 运营分析页 | `LX-D92C9E37C544` | 查询管理促销详情+listing+订单(批量) | POST | `/promotionApi/open/promotion/managementAllDetailBatch` | 查询管理促销详情+listing+订单(批量) |
| 运营分析页 | `LX-324AF6B69AEF` | 查询会员折扣or价格折扣详情+listing+订单(批量) | POST | `/promotionApi/open/promotion/primeDiscountAllDetailBatch` | 查询会员折扣or价格折扣详情+listing+订单(批量) |
| 运营分析页 | `LX-72966FDD4C29` | 查询秒杀详情+listing+订单(批量) | POST | `/promotionApi/open/promotion/secKillAllDetailBatch` | 查询秒杀详情+listing+订单(批量) |
| 运营分析页 | `LX-D1E4B7906B42` | 查询商品折扣列表 | POST | `/basicOpen/promotion/listingList` | 查询商品折扣列表 |
| 运营分析页 | `LX-03449E2EC06C` | 查询商品折扣详情-列表-优惠卷 | POST | `/basicOpen/promotion/listingDetailCoupon` | 查询商品折扣详情-列表-优惠卷 |
| 运营分析页 | `LX-020A91A14B42` | 查询商品折扣详情-列表-管理促销 | POST | `/basicOpen/promotion/listingDetailManage` | 查询商品折扣详情-列表-管理促销 |
| 运营分析页 | `LX-FE476B81237F` | 查询商品折扣详情-列表-会员折扣 | POST | `/basicOpen/promotion/listingDetailPrimeDiscount` | 查询商品折扣详情-列表-会员折扣 |
| 运营分析页 | `LX-A404B2104669` | 查询商品折扣详情-列表-秒杀 | POST | `/basicOpen/promotion/listingDetailSecKill` | 查询商品折扣详情-列表-秒杀 |
| 运营分析页 | `LX-8DD1FB86D648` | 查询预警消息列表-商品 | POST | `/basicOpen/settings/warningMessage/goodsList` | 查询预警消息列表-商品 |
| 运营分析页 | `LX-8F9A0C4E13C0` | 查询预警消息列表-库存 | POST | `/basicOpen/settings/warningMessage/inventoryList` | 查询预警消息列表-库存 |
| 运营分析页 | `LX-A5F6A7E6639A` | 查询利润统计-店铺 | POST | `/bd/profit/statistics/open/seller/list` | 支持查询新版利润统计的店铺维度 |
| 运营分析页 | `LX-1C7C9C7B770D` | 查询店铺汇总销量 | POST | `/erp/sc/data/sales_report/sales` | 支持按店铺维度查询店铺销量、销售额 |
| 运营分析页 | `LX-09FE9E838C58` | 查询订单利润-MSKU | POST | `/basicOpen/finance/mreport/OrderProfit` | 唯一键说明：sid+msku |
| 运营分析页 | `LX-5891B9352423` | 库存报表-本地仓-新报表-汇总 | POST | `/inventory/center/openapi/storageReport/local/aggregate/list` | 库存报表-本地仓-新报表-汇总 |
| 运营分析页 | `LX-FCDF84763AAF` | 库存报表-本地仓-新报表-明细 | POST | `/inventory/center/openapi/storageReport/local/detail/page` | 库存报表-本地仓-新报表-明细 |
| 运营分析页 | `LX-171BF687A225` | 库存报表-本地仓-历史报表-汇总 | POST | `/erp/sc/routing/inventoryLog/WareHouseReport/getLocalWareHouseSummaryList` | 库存报表-本地仓-历史报表-汇总 |
| 运营分析页 | `LX-0070B9951962` | 库存报表-本地仓-历史报表-明细 | POST | `/erp/sc/routing/inventoryLog/WareHouseReport/getLocalWareHouseDetailList` | 库存报表-本地仓-历史报表-明细 |
| 运营分析页 | `LX-CD4E8AC1BDC2` | 库存报表-海外仓-新报表-汇总 | POST | `/inventory/center/openapi/storageReport/overseas/aggregate/list` | 库存报表-海外仓-新报表-汇总 |
| 运营分析页 | `LX-8116408E9FBA` | 库存报表-海外仓-新报表-明细 | POST | `/inventory/center/openapi/storageReport/overseas/detail/page` | 库存报表-海外仓-新报表-明细 |
| 运营分析页 | `LX-A5CE884A505B` | 库存报表-海外仓-历史报表-汇总 | POST | `/erp/sc/routing/inventoryLog/WareHouseReport/getOverSeaSummaryList` | 库存报表-海外仓-历史报表-汇总 |
| 运营分析页 | `LX-3D1F244FB7C8` | 库存报表-海外仓-历史报表-明细 | POST | `/erp/sc/routing/inventoryLog/WareHouseReport/getOverSeaDetailList` | 库存报表-海外仓-历史报表-明细 |
| 运营分析页 | `LX-95A42DA552D3` | 查询采购报表列表 - 产品 | POST | `/basicOpen/report/purchase/product/list` | 查询采购报表列表 - 产品 |
| ... | ... | ... | ... | ... | 还有 3 行，完整见 `phase-1-candidate-apis.csv` |

### 采购

| 页面 | 接口ID | 接口名 | 方法 | 路径 | 说明 |
|---|---|---|---|---|---|
| 采购管理页 | `LX-D332F931885E` | 查询采购单列表 | POST | `/erp/sc/routing/data/local_inventory/purchaseOrderList` | 支持查询采购单列表，对应系统【采购】>【采购单】数据 |
| 采购管理页 | `LX-853A6501F0BF` | 查询采购退货单列表 | POST | `/erp/sc/routing/purchase/purchase_return_order/getPurchaseReturnOrderList` | 查询采购退货单列表 |
| 采购管理页 | `LX-B31DFDC39206` | 查询采购变更单列表 | POST | `/erp/sc/routing/purchase/purchaseChangeOrder/changeOrderList` | 查询采购变更单列表 |
| 采购管理页 | `LX-9BF4536568D4` | 查询委外订单列表 | POST | `/erp/sc/routing/purchase/purchaseOutsourceOrder/getOrders` | 查询委外订单列表 |
| 采购管理页 | `LX-96F32A1090F0` | 查询加工计划列表 | POST | `/basicOpen/openapi/workOrder/processPlanList` | 支持查询加工计划列表，对应系统【采购】加工计划列表数据。 |
| 采购管理页 | `LX-4B9473A2D2E1` | 查询收货单列表 | POST | `/erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/getOrderList` | 查询收货单列表 |
| 采购管理页 | `LX-95A42DA552D3` | 查询采购报表列表 - 产品 | POST | `/basicOpen/report/purchase/product/list` | 查询采购报表列表 - 产品 |

### 销售

| 页面 | 接口ID | 接口名 | 方法 | 路径 | 说明 |
|---|---|---|---|---|---|
| 销售与订单页 | `LX-71422945ADAC` | 查询Listing标签列表 | POST | `/basicOpen/globalTag/listing/page/list` | 查询Listing标签列表 |
| 销售与订单页 | `LX-EB69D6DC93FB` | 查询Listing操作日志列表 | POST | `/basicOpen/listingManage/listingOperateLog/pageList` | 查询Listing操作日志列表 |
| 销售与订单页 | `LX-C76D747AD0DA` | 刊登管理-获取指定 productType 的 JSON Schema | POST | `/basicOpen/openapi/publish/manage/getProductType` | 刊登管理-获取指定 productType 的 JSON Schema |
| 销售与订单页 | `LX-F560D3DA6DF1` | 查询优惠券详情+listing+订单(批量) | POST | `/promotionApi/open/promotion/couponAllDetailBatch` | 查询优惠券详情+listing+订单(批量) |
| 销售与订单页 | `LX-D92C9E37C544` | 查询管理促销详情+listing+订单(批量) | POST | `/promotionApi/open/promotion/managementAllDetailBatch` | 查询管理促销详情+listing+订单(批量) |
| 销售与订单页 | `LX-324AF6B69AEF` | 查询会员折扣or价格折扣详情+listing+订单(批量) | POST | `/promotionApi/open/promotion/primeDiscountAllDetailBatch` | 查询会员折扣or价格折扣详情+listing+订单(批量) |
| 销售与订单页 | `LX-72966FDD4C29` | 查询秒杀详情+listing+订单(批量) | POST | `/promotionApi/open/promotion/secKillAllDetailBatch` | 查询秒杀详情+listing+订单(批量) |
| 销售与订单页 | `LX-D1E4B7906B42` | 查询商品折扣列表 | POST | `/basicOpen/promotion/listingList` | 查询商品折扣列表 |
| 销售与订单页 | `LX-03449E2EC06C` | 查询商品折扣详情-列表-优惠卷 | POST | `/basicOpen/promotion/listingDetailCoupon` | 查询商品折扣详情-列表-优惠卷 |
| 销售与订单页 | `LX-020A91A14B42` | 查询商品折扣详情-列表-管理促销 | POST | `/basicOpen/promotion/listingDetailManage` | 查询商品折扣详情-列表-管理促销 |
| 销售与订单页 | `LX-FE476B81237F` | 查询商品折扣详情-列表-会员折扣 | POST | `/basicOpen/promotion/listingDetailPrimeDiscount` | 查询商品折扣详情-列表-会员折扣 |
| 销售与订单页 | `LX-A404B2104669` | 查询商品折扣详情-列表-秒杀 | POST | `/basicOpen/promotion/listingDetailSecKill` | 查询商品折扣详情-列表-秒杀 |
| 销售与订单页 | `LX-D332F931885E` | 查询采购单列表 | POST | `/erp/sc/routing/data/local_inventory/purchaseOrderList` | 支持查询采购单列表，对应系统【采购】>【采购单】数据 |
| 销售与订单页 | `LX-853A6501F0BF` | 查询采购退货单列表 | POST | `/erp/sc/routing/purchase/purchase_return_order/getPurchaseReturnOrderList` | 查询采购退货单列表 |
| 销售与订单页 | `LX-B31DFDC39206` | 查询采购变更单列表 | POST | `/erp/sc/routing/purchase/purchaseChangeOrder/changeOrderList` | 查询采购变更单列表 |
| 销售与订单页 | `LX-9BF4536568D4` | 查询委外订单列表 | POST | `/erp/sc/routing/purchase/purchaseOutsourceOrder/getOrders` | 查询委外订单列表 |
| 销售与订单页 | `LX-96F32A1090F0` | 查询加工计划列表 | POST | `/basicOpen/openapi/workOrder/processPlanList` | 支持查询加工计划列表，对应系统【采购】加工计划列表数据。 |
| 销售与订单页 | `LX-4B9473A2D2E1` | 查询收货单列表 | POST | `/erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/getOrderList` | 查询收货单列表 |
| 销售与订单页 | `LX-1C62776E886A` | 查询销售退货单列表 | POST | `/pb/mp/returns/v2/list` | 查询销售退货单列表 |
| 销售与订单页 | `LX-ECAEE8038F87` | 查询质检单列表 | POST | `/erp/sc/routing/deliveryReceipt/ReceiptOrderQc/getOrderList` | 查询质检单列表 |
| 销售与订单页 | `LX-5D311ED3B89E` | 查询质检单详情 | POST | `/basicOpen/qualityInspectionOrder/detail` | 查询质检单详情 |
| 销售与订单页 | `LX-A78D6BB9DC24` | 查询入库单列表 | POST | `/erp/sc/routing/storage/inbound/getOrders` | 查询入库单列表 |
| 销售与订单页 | `LX-179D3B8A9F63` | 查询出库单列表 | POST | `/erp/sc/routing/storage/outbound/getOrders` | 查询出库单列表 |
| 销售与订单页 | `LX-F23293A702BB` | 查询销售出库单详情 | POST | `/basicOpen/wmsOrder/getWmsOrdersByOrderNumbers` | 支持查询ERP中【仓库】>【销售出库单】数据，即自发货订单销售出库单 |
| 销售与订单页 | `LX-29AE97DABE08` | 加工单列表 | POST | `/erp/sc/routing/inventoryReceipt/StorageProcess/getOrderLists` | 加工单列表 |
| ... | ... | ... | ... | ... | 还有 18 行，完整见 `phase-1-candidate-apis.csv` |

## 下一步

将本清单与 `docs/data-sources/lingxing-walmart-api-to-system-data-map-draft.md` 和 `docs/data-sources/lingxing-walmart-api-to-system-data-map-draft.csv` 合并评估，优先选出第一个只读业务闭环
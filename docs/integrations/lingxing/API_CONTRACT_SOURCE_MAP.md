# Lingxing / Walmart API Contract Source Map

Status: repository evidence map; no external-call or implementation authorization
Generated: 2026-09-14

Each row reports whether normalized request/response evidence exists and whether the current classification can enter PRP planning. “Yes” never means provider verification or runtime authorization.

## Product

| Key | Interface | Path | Source doc | Request | Response | Status | Can enter PRP | Missing / risk |
|---|---|---|---|---|---|---|---|---|
| `LX-F6A548F96FD0` | 产品管理-查询透明计划商品列表 | `/basicOpen/product/getTransparencyProductList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-75F4963569A6` | 查询产品分类列表 | `/erp/sc/routing/data/local_inventory/category` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-82FF3AF996D2` | 查询产品品牌列表 | `/erp/sc/data/local_inventory/brand` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-226730376E6B` | 查询产品标签 | `/label/operation/v1/label/product/list` | `normalized CSV only` | No | Yes | `PARTIAL_CONTRACT` | No | `MISSING_REQUEST_PARAMS` |
| `LX-BD16C6D25A0D` | 查询产品辅料列表 | `/erp/sc/routing/data/local_inventory/productAuxList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-DA189364D1B7` | 查询捆绑产品关系列表 | `/erp/sc/routing/data/local_inventory/bundledProductList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-6F96FE519F29` | 查询操作日志 | `/basicOpen/product/getPagingLogLists` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-3F1F087FF8A1` | 查询本地产品列表 | `/erp/sc/routing/data/local_inventory/productList` | `old-system/source/docs/lingxing/ProductLists.md` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-95A42DA552D3` | 查询采购报表列表 - 产品 | `/basicOpen/report/purchase/product/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-8DD1FB86D648` | 查询预警消息列表-商品 | `/basicOpen/settings/warningMessage/goodsList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-320D9D20B37C` | 下载附件 | `/erp/sc/routing/common/file/download` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |

## ProductInfo

| Key | Interface | Path | Source doc | Request | Response | Status | Can enter PRP | Missing / risk |
|---|---|---|---|---|---|---|---|---|
| `LX-BB8D0DF598AF` | 批量查询本地产品详情 | `/erp/sc/routing/data/local_inventory/batchGetProductInfo` | `old-system/source/docs/lingxing/batchGetProductInfo.md` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-DCB0C142100B` | 查询本地产品详情 | `/erp/sc/routing/data/local_inventory/productInfo` | `old-system/source/docs/lingxing/ProductDetails.md` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |

## Listing

| Key | Interface | Path | Source doc | Request | Response | Status | Can enter PRP | Missing / risk |
|---|---|---|---|---|---|---|---|---|
| `LX-44D4A6C312C6` | 获取UPC编码列表 | `/listing/publish/api/upc/upcList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |

## Inventory

| Key | Interface | Path | Source doc | Request | Response | Status | Can enter PRP | Missing / risk |
|---|---|---|---|---|---|---|---|---|
| `LX-29AE97DABE08` | 加工单列表 | `/erp/sc/routing/inventoryReceipt/StorageProcess/getOrderLists` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-0070B9951962` | 库存报表-本地仓-历史报表-明细 | `/erp/sc/routing/inventoryLog/WareHouseReport/getLocalWareHouseDetailList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-171BF687A225` | 库存报表-本地仓-历史报表-汇总 | `/erp/sc/routing/inventoryLog/WareHouseReport/getLocalWareHouseSummaryList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-FCDF84763AAF` | 库存报表-本地仓-新报表-明细 | `/inventory/center/openapi/storageReport/local/detail/page` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-5891B9352423` | 库存报表-本地仓-新报表-汇总 | `/inventory/center/openapi/storageReport/local/aggregate/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-3D1F244FB7C8` | 库存报表-海外仓-历史报表-明细 | `/erp/sc/routing/inventoryLog/WareHouseReport/getOverSeaDetailList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-A5CE884A505B` | 库存报表-海外仓-历史报表-汇总 | `/erp/sc/routing/inventoryLog/WareHouseReport/getOverSeaSummaryList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-8116408E9FBA` | 库存报表-海外仓-新报表-明细 | `/inventory/center/openapi/storageReport/overseas/detail/page` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-CD4E8AC1BDC2` | 库存报表-海外仓-新报表-汇总 | `/inventory/center/openapi/storageReport/overseas/aggregate/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-A791179C9A78` | 查询AWD库存列表 | `/basicOpen/openapi/storage/awdWarehouseDetail` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-47310BFA3E0D` | 查询仓位库存明细 | `/erp/sc/routing/data/local_inventory/inventoryBinDetails` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-8DE4E360B561` | 查询仓位流水 | `/erp/sc/routing/data/local_inventory/wareHouseBinStatement` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-41E509578C0D` | 查询仓库列表 | `/erp/sc/data/local_inventory/warehouse` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-41B3AF612B29` | 查询仓库库存明细 | `/erp/sc/routing/data/local_inventory/inventoryDetails` | `old-system/source/docs/lingxing/InventoryDetails.md` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-EB2B3813F515` | 查询备货单详情 | `/basicOpen/overSeaWarehouse/stockOrder/detail` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-F0CE5B7F589B` | 查询库存流水（新） | `/erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-1181D4F827FB` | 查询批次明细 | `/erp/sc/routing/data/local_inventory/getBatchDetailList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-BCB9BCE2437F` | 查询批次流水 | `/erp/sc/routing/data/local_inventory/getBatchStatementList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-EC6F4C39346F` | 查询本地仓位列表 | `/erp/sc/routing/data/local_inventory/warehouseBin` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-D5353A465E6D` | 查询盘点单列表 | `/erp/sc/routing/inventoryReceipt/InventoryCheck/getOrderList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-642D33967219` | 查询盘点单详情 | `/erp/sc/routing/inventoryReceipt/InventoryCheck/getOrderDetail` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-4E3A3DA2B70A` | 查询调拨单列表 | `/erp/sc/routing/inventoryReceipt/StorageAllocation/getStorageAllocationList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-9909117FD1E7` | 查询调整单列表 | `/erp/sc/routing/inventoryReceipt/StorageAdjustment/getStorageAdjustOrderList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-8F9A0C4E13C0` | 查询预警消息列表-库存 | `/basicOpen/settings/warningMessage/inventoryList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-E95A3442D310` | 查询头程物流渠道列表 | `/erp/sc/data/local_inventory/channelList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-6F8ABDE7B566` | 查询库存流水（旧） | `/erp/sc/routing/data/local_inventory/wareHouseStatement` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |

## WFS / storage / inbound transport

| Key | Interface | Path | Source doc | Request | Response | Status | Can enter PRP | Missing / risk |
|---|---|---|---|---|---|---|---|---|
| `LX-531E7CE81EF4` | 查询WFS库存列表 | `/cepf/warehouse/api/openApi/queryWFSInventionPage` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-CF87F80AD608` | 查询产品仓位列表 | `/basicOpen/warehouseConfig/warehouseBin/getEntryRecommendBinList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-A4D3F436FF1F` | 查询产品属性列表 | `/erp/sc/routing/storage/attribute/attributeList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-A78D6BB9DC24` | 查询入库单列表 | `/erp/sc/routing/storage/inbound/getOrders` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-179D3B8A9F63` | 查询出库单列表 | `/erp/sc/routing/storage/outbound/getOrders` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-96F32A1090F0` | 查询加工计划列表 | `/basicOpen/openapi/workOrder/processPlanList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-ACB0219BB470` | 查询备货单收货记录 | `/erp/sc/routing/owms/inbound/getReceiveGoodRecords` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-E5E2F516B966` | 查询备货单装箱信息 | `/erp/sc/routing/owms/inbound/getPackingData` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-5AFC6979F657` | 查询多属性产品列表 | `/erp/sc/routing/storage/spu/spuList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-30AF347E45FE` | 查询多属性产品详情 | `/erp/sc/routing/storage/spu/info` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-7773B7A1FDF9` | 查询海外仓备货单列表 | `/erp/sc/routing/owms/inbound/listInbound` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-DE77858CC887` | 查询移除入库单列表 | `/erp/sc/routing/owms/removalInbound/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-814E67414272` | 查询系统产品与第三方海外仓产品映射列表 | `/erp/sc/routing/owms/inbound/matchSkuList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-5D311ED3B89E` | 查询质检单详情 | `/basicOpen/qualityInspectionOrder/detail` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-FD9302CF208A` | 查询销售出库单列表 | `/erp/sc/routing/wms/order/wmsOrderList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-F596F7E8C481` | 查询销售出库单物流面单 | `/erp/sc/routing/wms/order/getWmsLogisticsLabels` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-F23293A702BB` | 查询销售出库单详情 | `/basicOpen/wmsOrder/getWmsOrdersByOrderNumbers` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-EBADE37CF17C` | 获取备货单号 | `/erp/sc/routing/owms/inbound/listOrderNos` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-AAFAE3E2B6D6` | 获取第三方SKU标签PDF文件 | `/erp/sc/routing/owms/inbound/productLabel` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-BED54283FB2B` | 获取第三方箱唛 | `/erp/sc/routing/owms/inbound/packageLabel` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-75157159D29E` | 获取自定义入库类型 | `/erp/sc/routing/storage/inbound/getCustomTypes` | `normalized CSV only` | No | Yes | `PARTIAL_CONTRACT` | No | `MISSING_REQUEST_PARAMS` |
| `LX-10C1BC0E9648` | 获取自定义出库类型 | `/erp/sc/routing/storage/outbound/getCustomTypes` | `normalized CSV only` | No | Yes | `PARTIAL_CONTRACT` | No | `MISSING_REQUEST_PARAMS` |
| `LX-051118326D63` | 装箱任务-任务列表 | `/basicOpen/packingTask/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-8C46310BDBDA` | 装箱任务-任务详情 | `/basicOpen/packingTask/taskDetail` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-081EC270CC8F` | 头程对账列表 | `/basicOpen/logistics/headLogisticsReconciliation/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-C95DBD64F2A9` | 查询WFS货件列表 | `/cepf/warehouse/api/openApi/queryWFSCargoPage` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-725F26FDC523` | 查询物流-头程物流商 | `/basicOpen/logistics/headLogisticsProvider/query/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-7F9838344C2B` | 查询运输方式列表 | `/basicOpen/businessConfig/transportMethod/list` | `normalized CSV only` | No | Yes | `PARTIAL_CONTRACT` | No | `MISSING_REQUEST_PARAMS` |
| `LX-2B737D7329A7` | 获取快速出库结果 | `/pb/mp/order/v2/getFastOutboundResult` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |

## Sales / Order

| Key | Interface | Path | Source doc | Request | Response | Status | Can enter PRP | Missing / risk |
|---|---|---|---|---|---|---|---|---|
| `LX-C76D747AD0DA` | 刊登管理-获取指定 productType 的 JSON Schema | `/basicOpen/openapi/publish/manage/getProductType` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-EB69D6DC93FB` | 查询Listing操作日志列表 | `/basicOpen/listingManage/listingOperateLog/pageList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-71422945ADAC` | 查询Listing标签列表 | `/basicOpen/globalTag/listing/page/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-F560D3DA6DF1` | 查询优惠券详情+listing+订单(批量) | `/promotionApi/open/promotion/couponAllDetailBatch` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-324AF6B69AEF` | 查询会员折扣or价格折扣详情+listing+订单(批量) | `/promotionApi/open/promotion/primeDiscountAllDetailBatch` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-D1E4B7906B42` | 查询商品折扣列表 | `/basicOpen/promotion/listingList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-03449E2EC06C` | 查询商品折扣详情-列表-优惠卷 | `/basicOpen/promotion/listingDetailCoupon` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-FE476B81237F` | 查询商品折扣详情-列表-会员折扣 | `/basicOpen/promotion/listingDetailPrimeDiscount` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-A404B2104669` | 查询商品折扣详情-列表-秒杀 | `/basicOpen/promotion/listingDetailSecKill` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-020A91A14B42` | 查询商品折扣详情-列表-管理促销 | `/basicOpen/promotion/listingDetailManage` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-9BF4536568D4` | 查询委外订单列表 | `/erp/sc/routing/purchase/purchaseOutsourceOrder/getOrders` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-C4DB859443E2` | 查询平台订单列表 | `/cepfPlatformOrder/open-api/newPlatformOrder/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-1C7C9C7B770D` | 查询店铺汇总销量 | `/erp/sc/data/sales_report/sales` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-72966FDD4C29` | 查询秒杀详情+listing+订单(批量) | `/promotionApi/open/promotion/secKillAllDetailBatch` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-D92C9E37C544` | 查询管理促销详情+listing+订单(批量) | `/promotionApi/open/promotion/managementAllDetailBatch` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-5C93F09C1D1B` | 查询订单管理订单列表 | `/pb/mp/order/v2/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-D332F931885E` | 查询采购单列表 | `/erp/sc/routing/data/local_inventory/purchaseOrderList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-B31DFDC39206` | 查询采购变更单列表 | `/erp/sc/routing/purchase/purchaseChangeOrder/changeOrderList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-074FA24909F1` | 刊登管理-获取运费模板 | `/basicOpen/openapi/publish/manage/getMerchantShippingGroup` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-2EDE9B89E52C` | 查询促销活动列表-优惠券 | `/basicOpen/promotionalActivities/coupon/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-4D53DF8CE668` | 查询促销活动列表-会员折扣/价格折扣 | `/basicOpen/promotionalActivities/vipDiscount/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-14EF57136BD3` | 查询促销活动列表-秒杀 | `/basicOpen/promotionalActivities/secKill/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-1DC5C91C2FE2` | 查询促销活动列表-管理促销 | `/basicOpen/promotionalActivities/manage/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-D806EDEB25E4` | 查询调价队列 | `/basicOpen/module/adjustPrice/AdjustPriceManual` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-A4FD6B748623` | 查询销量统计列表v2 | `/basicOpen/platformStatisticsV2/saleStat/pageList` | `old-system/source/docs/lingxing/PlatformStatisticsSaleStatPageListV2.md` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-EFB08467128D` | 多渠道订单-交易明细 | `/basicOpen/openapi/salesOrder/multi-channel/list/transaction` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |

## Finance

| Key | Interface | Path | Source doc | Request | Response | Status | Can enter PRP | Missing / risk |
|---|---|---|---|---|---|---|---|---|
| `LX-63E99B54ED72` | Walmart-查询回款明细列表 | `/basicOpen/multiplatformFinance/walmart/bill/payout/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-727003CFF7B4` | Walmart-查询结算账单列表 | `/basicOpen/multiplatformFinance/walmart/bill/statement/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-27FD5B4A5146` | 查询利润报表 - 订单维度transaction视图 | `/basicOpen/finance/profitReport/order/transcation/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-E67765C12B1D` | 查询利润报表-店铺 | `/bd/profit/report/open/report/seller/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-69B7BDB30BF3` | 查询利润报表-店铺月度汇总 | `/bd/profit/report/open/report/seller/summary/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-F30C3A5673B7` | 查询利润报表-订单 | `/bd/profit/report/open/report/order/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-A5F6A7E6639A` | 查询利润统计-店铺 | `/bd/profit/statistics/open/seller/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-DB6D62E9EE37` | 查询结算利润（利润报表）-订单 | `/basicOpen/multiplatform/profit/report/order` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-09FE9E838C58` | 查询订单利润-MSKU | `/basicOpen/finance/mreport/OrderProfit` | `old-system/source/docs/lingxing/OrderProfitListMSKU.md` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-598C49EB1197` | 查询请款单列表 | `/basicOpen/finance/requestFunds/order/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-5D552F4D7A8D` | 利润报表-列表配置查询 | `/basicOpen/finance/profitReport/config` | `normalized CSV only` | No | Yes | `PARTIAL_CONTRACT` | No | `MISSING_REQUEST_PARAMS` |
| `LX-0BB27D85E792` | 利润报表-明细列表查询 | `/basicOpen/finance/settlement/profitList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-CEFCD4ABAF61` | 应收报告-列表查询 | `/bd/sp/api/open/monthly/receivable/report/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-B30E9E6803D0` | 应收报告-详情-列表 | `/bd/sp/api/open/monthly/receivable/report/list/detail` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-0F0DF3FDD859` | 应收报告-详情-基础信息 | `/bd/sp/api/open/monthly/receivable/report/list/detail/info` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-2AD144D844C7` | 查询settlement下载URL | `/bd/sp/api/open/settlement/export/url/get` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-A453FAE8A107` | 查询利润报表-SKU | `/bd/profit/report/open/report/sku/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-3D58C3293860` | 查询利润统计-MSKU | `/bd/profit/statistics/open/msku/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-B7DA9DE52C6A` | 查询可用报告列表 - Walmart Payment | `/cepf/fms/openapi/walmartPayment/queryReport` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-66894A74C546` | 查询报告详情 - Walmart Payment | `/cepf/fms/openapi/walmartPayment/queryPage` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-FF6962F51900` | 查询收款单列表 | `/basicOpen/finance/queryReceiptFundsList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-DEF946C2CC04` | 查询结算利润（利润报表）-msku | `/basicOpen/multiplatform/profit/report/msku` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-61200503BD63` | 查询结算利润（利润报表）-sku | `/basicOpen/multiplatform/profit/report/sku` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-62F91F9CB35B` | 查询请款池 - 货款月结 | `/basicOpen/finance/requestFundsPool/inbound/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-92FE8988B86C` | 查询请款池 - 货款现结 | `/basicOpen/finance/requestFundsPool/purchase/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-9C950113F6EA` | 查询请款池 - 货款预付款 | `/basicOpen/finance/requestFundsPool/prepay/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-D0E648500CCA` | 查询请款池-其他应付款 | `/basicOpen/finance/requestFundsPool/customFee/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-0A3BA5A66954` | 查询请款池-其他费用 | `/basicOpen/finance/requestFundsPool/otherFee/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-A095838ED68E` | 查询请款池-物流请款 | `/basicOpen/finance/requestFundsPool/logistics/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-A623F7D01F1B` | 查询费用明细列表 | `/bd/fee/management/open/feeManagement/otherFee/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-022E3FB1A8C6` | 查询费用类型列表 | `/bd/fee/management/open/feeManagement/otherFee/type` | `normalized CSV only` | No | Yes | `PARTIAL_CONTRACT` | No | `MISSING_REQUEST_PARAMS` |
| `LX-CDEC1BCCBD6A` | 获取国家下的州、省编码 | `/basicOpen/multiplatform/profit/report/stateList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-C158E1CD652D` | 查询利润报表（旧） - MSKU | `/erp/sc/routing/finance/ProfitState/profitMsku` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-E9129B6BC59E` | 查询利润报表（旧）-结算明细 | `/erp/sc/routing/finance/ProfitState/profitSettlement` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-F9F6C21DEC55` | 查询利润统计（旧）-MSKU | `/erp/sc/routing/finance/ProfitStatis/profitMsku` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-77BF3BD27008` | 查询结算利润（利润报表）-店铺（旧版） | `/basicOpen/multiplatform/profit/report/seller` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |

## Ads

| Key | Interface | Path | Source doc | Request | Response | Status | Can enter PRP | Missing / risk |
|---|---|---|---|---|---|---|---|---|
| `LX-4EDA0C221DF4` | 关键词列表 | `/erp/sc/routing/tool/toolKeywordRank/getKeywordList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-2454C40DBB80` | 查询广告发票列表 | `/bd/profit/report/open/report/ads/invoice/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-7106755764A4` | 查询广告发票基本信息 | `/bd/profit/report/open/report/ads/invoice/detail` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-A8A460011763` | 查询广告发票活动列表 | `/bd/profit/report/open/report/ads/invoice/campaign/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-1AD86690E18F` | 查询沃尔玛-广告 - SB广告 - 关键词 | `/basicOpen/multiplatform/ads/reportKeywordSbList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-5182D556071A` | 查询沃尔玛-广告 - SB广告 - 平台 | `/basicOpen/multiplatform/ads/reportPlatformSbList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-EAFAEC4B71CF` | 查询沃尔玛-广告 - SB广告 - 广告 | `/basicOpen/multiplatform/ads/reportAdItemSbList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-FD59C74A55D7` | 查询沃尔玛-广告 - SB广告 - 广告活动 | `/basicOpen/multiplatform/ads/reportCampaignSbList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-7C855BFAF5AA` | 查询沃尔玛-广告 - SB广告 - 广告组 | `/basicOpen/multiplatform/ads/reportAdGroupSbList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-6D6235392322` | 查询沃尔玛-广告 - SB广告 - 页面类型 | `/basicOpen/multiplatform/ads/reportPageTypeSbList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-434F316A392B` | 查询沃尔玛-广告 - SP广告 - 关键词 | `/basicOpen/multiplatform/ads/reportKeywordSpList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-646C5878A4CE` | 查询沃尔玛-广告 - SP广告 - 平台 | `/basicOpen/multiplatform/ads/reportPlatformSpList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-0CB86D55776C` | 查询沃尔玛-广告 - SP广告 - 广告 | `/basicOpen/multiplatform/ads/reportAdItemSpList` | `old-system/source/docs/lingxing/MultiPlatform/Advertisement/walmart-reportAdItemSpList_17.md` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-058A66EC8E8E` | 查询沃尔玛-广告 - SP广告 - 广告活动 | `/basicOpen/multiplatform/ads/queryCampaignSpList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-31720B315BD9` | 查询沃尔玛-广告 - SP广告 - 广告组 | `/basicOpen/multiplatform/ads/queryGroupSpList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-5779B4C3F664` | 查询沃尔玛-广告 - SP广告 - 页面类型 | `/basicOpen/multiplatform/ads/queryPageTypeSPList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-DD135F34D7C2` | 查询沃尔玛-广告 - SV广告 - 关键词 | `/basicOpen/multiplatform/ads/reportKeywordSvList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-F47DF22109CA` | 查询沃尔玛-广告 - SV广告 - 平台 | `/basicOpen/multiplatform/ads/reportPlatformSvList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-40C3F27491DD` | 查询沃尔玛-广告 - SV广告 - 广告 | `/basicOpen/multiplatform/ads/reportAdItemSvList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-86309AAB2BAC` | 查询沃尔玛-广告 - SV广告 - 广告活动 | `/basicOpen/multiplatform/ads/reportCampaignSvList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-541F3B11E6DE` | 查询沃尔玛-广告 - SV广告 - 广告组 | `/basicOpen/multiplatform/ads/queryAdGroupSvList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-83BBCE9FCB0E` | 查询沃尔玛-广告 - SV广告 - 页面类型 | `/basicOpen/multiplatform/ads/queryReportPageTypeSvList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-48F40DDAE6D3` | 查询沃尔玛-词 - 沃尔玛热门搜索词 | `/basicOpen/multiplatform/ads/reportSearchTrendsList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-1DC15769BD57` | 查询沃尔玛广告主列表 | `/basicOpen/adReport/advertiser/list` | `old-system/source/docs/lingxing/WalmartQueryAdvertiserList.md` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |

## After-sales

| Key | Interface | Path | Source doc | Request | Response | Status | Can enter PRP | Missing / risk |
|---|---|---|---|---|---|---|---|---|
| `LX-571E669C2E50` | 多平台-Walmart售后订单列表 | `/basicOpen/openapi/multiplatform/walmart/returnOrder/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-5470F505D06E` | 查询售后工单列表 | `/pb/mp/returns/workOrder/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-EA8918986608` | 查询店铺绩效列表 | `/basicOpen/customerService/storeTarget/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-54F0AD822356` | 查询店铺绩效详情 | `/basicOpen/customerService/storeTarget/detail` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-853A6501F0BF` | 查询采购退货单列表 | `/erp/sc/routing/purchase/purchase_return_order/getPurchaseReturnOrderList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-1C62776E886A` | 查询销售退货单列表 | `/pb/mp/returns/v2/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-B5184BA8522B` | 统计-查询退货分析 | `/basicOpen/salesAnalysis/returnOrder/analysisLists` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-A8485DB1E3D3` | 查询RMA管理 | `/basicOpen/customerService/rmaManage/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-CD351FB7F89D` | 查询业绩通知列表 | `/basicOpen/customerService/performanceNotice/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-EF34B93FBA6A` | 查询买家之声列表 | `/basicOpen/customerService/voiceOfBuyer/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-95DD19D356E9` | 查询客户列表（新） | `/basicOpen/customerService/crm/customer/index` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-D27EF46B3ADF` | 查询评价管理 4-5星Feedback列表 | `/erp/sc/cs/feedback/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-B75C246341A6` | 查询评价统计-Feedback列表 | `/erp/sc/cs/feedbackReport/lists` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-BFDF4705FFBD` | 查询评价统计-Feedback每日新增数 | `/erp/sc/cs/feedbackReport/detail` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-2C7CF1CE8AAE` | 查询评价统计-Review列表 | `/erp/sc/v2/cs/reviewReport/lists` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-2D4837A1809E` | 查询评价统计-Review每日新增数 | `/erp/sc/cs/reviewReport/detail` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-4BEBA8523762` | 查询退件地址列表 | `/basicOpen/multiplatform/address/returnAddressList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-61BD491411AA` | 查询邮件列表 | `/erp/sc/data/mail/lists` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-5F14BE8D2BD0` | 查询邮件详情 | `/erp/sc/data/mail/detail` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-C1830CE93E50` | 查询客户列表（旧） | `/bd/crm/open/api/customer/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |

## Store / Seller / Marketplace

| Key | Interface | Path | Source doc | Request | Response | Status | Can enter PRP | Missing / risk |
|---|---|---|---|---|---|---|---|---|
| `LX-C3C3157EC484` | 店铺维度-查询目标 | `/bd/goal/management/open/store/batchSelect` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-1524E1C3FF10` | 查询Walmart产品表现 | `/basicOpen/platformStatistics/walmartProductAnalysis/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-9212623D77EA` | 查询Walmart在线商品 | `/basicOpen/multiplatform/walmart/list` | `old-system/source/docs/lingxing/walmartList.md` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-F8354824E040` | 查询多平台店铺信息 | `/pb/mp/shop/v2/getSellerList` | `old-system/source/docs/lingxing/StoreInfoV2.md` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-6EFCDB06A626` | 查询Walmart Review列表 | `/basicOpen/multiplatform/walmart/queryCommentList` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |

## Other

| Key | Interface | Path | Source doc | Request | Response | Status | Can enter PRP | Missing / risk |
|---|---|---|---|---|---|---|---|---|
| `LX-A07E627F7B70` | 定制化附件下载接口 | `/erp/sc/routing/customized/file/download` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-04CE920F9507` | 查询ERP用户信息列表 | `/erp/sc/data/account/lists` | `normalized CSV only` | No | Yes | `PARTIAL_CONTRACT` | No | `MISSING_REQUEST_PARAMS` |
| `LX-B70161F2CA8D` | 查询供应商列表 | `/erp/sc/data/local_inventory/supplier` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-FC39BD159D05` | 查询报告 | `/openReport/report/task/getReport` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-001128D990D5` | 查询竞品监控列表 | `/basicOpen/tool/competitiveMonitor/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-766F8D291DF3` | 查询采购报表列表 - 供应商 | `/basicOpen/report/purchase/supplier/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-DCA6FEF9EA75` | 查询采购报表列表 - 采购员 | `/basicOpen/report/purchase/buyer/list` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-223398DA3539` | 查询采购方列表 | `/erp/sc/routing/data/purchaser/lists` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-03B82747B50A` | 查询采购计划列表 | `/erp/sc/routing/data/local_inventory/getPurchasePlans` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-9118DDA102D0` | 获取 access-token和refresh-token | `/api/auth-server/oauth/access-token` | `old-system/source/docs/lingxing/GetToken.md` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-CEFFEEDBFB8D` | 负责人维度-查询目标 | `/bd/goal/management/open/user/batchSelect` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |
| `LX-5852A627B6FE` | 续约接口令牌 | `/api/auth-server/oauth/refresh` | `normalized CSV only` | Yes | Yes | `READY_FOR_PRP` | Yes | `AUTH_UNKNOWN` |

## Not use / Deleted / Not Walmart

| Key | Interface | Path | Source doc | Request | Response | Status | Can enter PRP | Missing / risk |
|---|---|---|---|---|---|---|---|---|
| `LX-678C78868D7F` | Lazada广告-获取广告商品信息 | `/basicOpen/lazadaAd/item/info` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-EAB2A6D42662` | Lazada广告-获取店铺信息 | `/basicOpen/lazadaAd/seller/info` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-8349E3853708` | SD商品定位报表 | `/pb/openapi/newad/sdTargetReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-5380CB6A41A8` | SD已购买商品报表 | `/pb/openapi/newad/sdAsinReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E6C0FF738B16` | SD广告商品报表 | `/pb/openapi/newad/sdProductAdReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-11CEDDBE86D1` | SP商品定位报表 | `/pb/openapi/newad/spTargetReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-4699407015B7` | SP已购买商品报表 | `/pb/openapi/newad/asinReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-32025D28AF75` | SP广告商品报表 | `/pb/openapi/newad/spProductAdReports` | `old-system/source/docs/lingxing/spProductAdReports.md` | Yes | Yes | `DELETED` | No | `DELETED` |
| `LX-9AC6BE805FBF` | 分页查询店铺报告列表 | `/basicOpen/multiplatform/ads/shopee/store/report/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D0FD5B698B84` | 查询DSP报告列表-订单 | `/basicOpen/dspReport/order/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-7152C6591169` | 查询TikTok-GMV MAX-广告商品 | `/basicOpen/multiplatform/ads/queryGmvItemGroupReportList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-5238E2EC1CE5` | 查询TikTok-GMV MAX-店铺列表 | `/basicOpen/multiplatform/ads/queryGmvStoreList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2DA803B0B95B` | Lazada广告-关键词报告 | `/basicOpen/lazadaAd/keyword/report/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A429D13382E7` | Lazada广告-受众报告 | `/basicOpen/lazadaAd/audience/report/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-B6E76EA85894` | Lazada广告-广告商品报告 | `/basicOpen/lazadaAd/item/report/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-69354216416E` | Lazada广告-广告活动报告 | `/basicOpen/lazadaAd/campaign/report/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-CE9EC5C49C4C` | Lazada广告-店铺报告 | `/basicOpen/lazadaAd/store/report/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-36563DAFE486` | Lazada广告-获取广告活动信息 | `/basicOpen/lazadaAd/campaign/info` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2C76574F71C3` | SB关键词-广告位报告 | `/pb/openapi/newad/listHsaKeywordPlacementReport` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D5802011AD7B` | SB分摊 | `/pb/openapi/newad/sbDivideAsinReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-0CA18307F7A5` | SB广告位小时数据 | `/pb/openapi/newad/sbAdPlacementHourData` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-B1DDA380B49A` | SB广告创意 | `/pb/openapi/newad/hsaProductAds` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-CA835F6E81F2` | SB广告创意报告 | `/pb/openapi/newad/listHsaProductAdReport` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-081CA1E01E59` | SB广告归因于广告的购买报告 | `/pb/openapi/newad/hsaPurchasedAsinReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-AE3D4AE5923A` | SB广告活动 | `/pb/openapi/newad/hsaCampaigns` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-FE294868EC86` | SB广告活动-广告位报告 | `/pb/openapi/newad/hsaCampaignPlacementReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-1E023FC3D19A` | SB广告活动小时数据 | `/pb/openapi/newad/sbCampaignHourData` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C950D8D237D2` | SB广告活动报表 | `/pb/openapi/newad/hsaCampaignReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-5D8D390AB316` | SB广告的投放 | `/pb/openapi/newad/sbTargeting` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A95DBBBEAB65` | SB广告的投放报告 | `/pb/openapi/newad/listHsaTargetingReport` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E5CEAED0EF1C` | SB广告组 | `/pb/openapi/newad/hsaAdGroups` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C9638FBFB409` | SB广告组小时数据 | `/pb/openapi/newad/sbAdGroupHourData` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-F12CABEAD851` | SB广告组报表 | `/pb/openapi/newad/hsaAdGroupReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-BC26A7360C61` | SB用户搜索词报表 | `/pb/openapi/newad/hsaQueryWordReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-50D26DEA4A44` | SD匹配的目标报表 | `/pb/openapi/newad/sdMatchTargetReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C1DB5C9E8689` | SD广告商品 | `/pb/openapi/newad/sdProductAds` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-3666EC6CF367` | SD广告小时数据 | `/pb/openapi/newad/sdAdvertiseHourData` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-8886AA112D0B` | SD广告活动 | `/pb/openapi/newad/sdCampaigns` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-683AC66EF916` | SD广告活动小时数据 | `/pb/openapi/newad/sdCampaignHourData` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E0BADE8A2D2E` | SD广告活动报表 | `/pb/openapi/newad/sdCampaignReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-7AFEB8F0F72E` | SD广告组 | `/pb/openapi/newad/sdAdGroups` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-089548657F54` | SD广告组小时数据 | `/pb/openapi/newad/sdAdGroupHourData` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-EBCD04C65F4E` | SD广告组报表 | `/pb/openapi/newad/sdAdGroupReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-8BB06733247F` | SP关键词报表 | `/pb/openapi/newad/spKeywordReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A1D292BDA8E7` | SP广告位小时数据 | `/pb/openapi/newad/spAdPlacementHourData` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-105B76D1B35F` | SP广告位报告 | `/pb/openapi/newad/campaignPlacementReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-48768797B0AD` | SP广告否定投放（ASIN） | `/basicOpen/adReport/spTarget/addNegativeTargets` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D0C19BD07910` | SP广告否定词归档 | `/basicOpen/adReport/spTarget/archiveNegatives` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D829D61656DF` | SP广告商品 | `/pb/openapi/newad/spProductAds` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-5F9FB329CC07` | SP广告小时数据 | `/pb/openapi/newad/spAdvertiseHourData` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-AC04F2FEE378` | SP广告活动 | `/pb/openapi/newad/spCampaigns` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-B85589C6BB4D` | SP广告活动小时数据 | `/pb/openapi/newad/spCampaignHourData` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-3E6843A8C9D5` | SP广告活动报表 | `/pb/openapi/newad/spCampaignReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-406619228BA7` | SP广告组 | `/pb/openapi/newad/spAdGroups` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-783BFCE74EAA` | SP广告组小时数据 | `/pb/openapi/newad/spAdGroupHourData` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-64E265301BB4` | SP广告组报表 | `/pb/openapi/newad/spAdGroupReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-90910B1B184B` | SP用户搜索词报表 | `/pb/openapi/newad/queryWordReports` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-65212D74C69C` | 分页查询广告活动报告列表 | `/basicOpen/multiplatform/ads/shopee/campaign/report/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-7B74822BC7D8` | 广告分析-关键词分析 | `/basicOpen/adReport/analyze/keyword` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-32B0211085C2` | 广告分析-搜索词分析 | `/basicOpen/adReport/analyze/searchTerm` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D4CCE5E32FEF` | 广告组合 | `/pb/openapi/newad/portfolios` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E57F75843A1E` | 查询DSP广告主列表 | `/newad/dspAdvertiserList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C7CF27891143` | 查询TikTok-GMV MAX-广告帐号 | `/basicOpen/multiplatform/ads/queryGmvAdvertiserReportList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D9AA1ED2CEE4` | 查询TikTok-GMV MAX-推广系列 | `/basicOpen/multiplatform/ads/queryGmvCampaignReportList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-3FB27E07164F` | 查询TikTok-推广广告-广告 | `/basicOpen/multiplatform/ads/queryTiktokAdList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-90C0E7FD777B` | 查询TikTok-推广广告-广告帐号 | `/basicOpen/multiplatform/ads/queryAdvertiserList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C07CE62AA6EA` | 查询TikTok-推广广告-广告帐号 | `/basicOpen/multiplatform/ads/queryCommonAdvertiserList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-1BB66404CC4A` | 查询TikTok-推广广告-广告系列 | `/basicOpen/multiplatform/ads/queryTiktokCampaignList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A6B9EE3C2926` | 查询TikTok-推广广告-广告组 | `/basicOpen/multiplatform/ads/queryTiktokAdGroupList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-DA80CC5D8249` | 查询广告账号列表 | `/basicOpen/baseData/account/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-BAB1AFEA4490` | 调整sp广告组 | `/basicOpen/adReport/manage/putSpAdGroup` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-4F932AB13FCE` | SP广告添加关键词 | `/basicOpen/adReport/spTarget/addKeywords` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-9B2B325174AF` | SP广告添加否定关键词 | `/basicOpen/adReport/spTarget/addNegativeKeywords` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-77D84796C284` | 修改SB关键词 | `/basicOpen/adReport/manage/putSbKeyword` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-68F78F02925A` | 修改SB商品投放 | `/basicOpen/adReport/manage/putSbTarget` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A086D2CBB4EC` | 修改SB广告活动 | `/basicOpen/adReport/manage/putSbCampaign` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-62DA50F7AD5B` | 修改SB广告组 | `/basicOpen/adReport/manage/putSbAdGroup` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-852FFA5E34CB` | 修改SP广告活动和广告位 | `/basicOpen/adReport/manage/putSpCampaign` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-9013709AEFEC` | 修改广告商品状态 | `/basicOpen/adReport/manage/putSpProductAds` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-5B1A57608128` | ABA搜索词报告-按周维度 | `/pb/openapi/newad/abaReport` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-99DE9196BEAB` | SB否定关键词 | `/pb/openapi/newad/hsaNegativeKeywords` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-DC99443FEE80` | SB否定商品投放 | `/pb/openapi/newad/hsaNegativeTargets` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-8C083D800F51` | SB投放小时数据 | `/pb/openapi/newad/sbTargetHourData` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-9712027ED36A` | SD否定商品定位 | `/pb/openapi/newad/sdNegativeTargets` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E03740968D3D` | SD商品定位 | `/pb/openapi/newad/sdTargets` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E47272E9B0EB` | SD投放小时数据 | `/pb/openapi/newad/sdTargetHourData` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-9876BC615E36` | SP关键词 | `/pb/openapi/newad/spKeywords` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2990FD9F2130` | SP否定投放 | `/pb/openapi/newad/spNegativeTargetsOrKeywords` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-0DA11D7BA5E8` | SP商品定位 | `/pb/openapi/newad/spTargets` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-AFC62F397A4F` | SP投放小时数据 | `/pb/openapi/newad/spTargetHourData` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-0D3676DC1081` | 出单时段分析（产品） | `/basicOpen/adReport/productOrderAnalysis/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A80B42AB7531` | 操作日志（新） | `/pb/openapi/newad/apiLogStandard` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A59140DD8234` | 调整sp关键词 | `/adReport/manage/putSpKeyword` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-BB33A112C1A5` | 调整sp商品投放 | `/adReport/manage/putSpTarget` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-08C95686A98A` | 多平台-Shopify售后订单列表 | `/basicOpen/openapi/multiplatform/shopify/returnOrder/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2FDB59055008` | 多平台-Temu售后订单列表 | `/basicOpen/openapi/multiplatform/temu/returnOrder/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E9E374CFDEAA` | 多平台-TikTok售后订单列表 | `/basicOpen/openapi/multiplatform/tiktok/returnOrder/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E195EA366FB4` | 查询VC店铺列表 | `/basicOpen/platformAuth/vcSeller/pageList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-88B94684C494` | 查询亚马逊多渠道订单详情-商品信息 | `/order/amzod/api/orderDetails/productInformation` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-0D2A0F1E6634` | 查询亚马逊多渠道订单详情-物流信息 | `/order/amzod/api/orderDetails/logisticsInformation` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-00F90E33DDB2` | 查询亚马逊多渠道订单详情-退货换货信息 | `/order/amzod/api/orderDetails/returnInformation` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-9C404AD3900F` | 查询亚马逊源报表-FBA退货订单 | `/erp/sc/data/mws_report/refundOrders` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A54E22CE74C6` | 查询亚马逊源报表-FBM退货订单 | `/erp/sc/routing/data/order/fbmReturnOrderList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E41560429B6B` | 查询售后订单列表 | `/erp/sc/routing/amzod/order/afterSaleList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-DD7ED95CB9C6` | Temu半托-退货面单费 | `/basicOpen/multiplatformFinance/temuHalf/return/fee/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-BE1057CB168C` | 待收货退货单快捷入库 | `/basicOpen/return/order/fastStorageIn` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-F9AD2E4B84C4` | 更新订单客服备注 | `/pb/mp/order/setRemark` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-37CEB6603EA8` | 查询STA任务包装组装箱信息 | `/amzStaServer/openapi/inbound-plan/listInboundPlanGroupPacking` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-4B0D825FD71B` | 查询asin360小时数据 | `/basicOpen/salesAnalysis/productPerformance/performanceTrendByHour` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A7F6D3992956` | 查询评价管理 1-3星Feedback列表 | `/erp/sc/cs/feedback/listMws` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2DB33EF69D2A` | 查询评价管理-Review | `/erp/sc/v2/data/mws/reviews` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-9A3D1D8B2F7F` | 查询评论管理 - Review(新) | `/basicOpen/openapi/service/v3/data/mws/reviews` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E6696C712FDB` | 订单退款 | `/basicOpen/openapi/salesOrder/refundOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `side_effect_endpoint; not eligible for read-only sync PRP; requires separate owner approval if ever needed` |
| `LX-C3A80433378D` | 作废采购/委外退货单 | `/basicOpen/purchase/cancelPurchaseReturnOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-AB7E08BE0696` | 创建已完成的采购退货单 | `/erp/sc/routing/purchase/purchase_return_order/createPurchaseReturnOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-51D280C19061` | 判断是否提交人自选 | `/basicOpen/customerService/workOrder/auditFlow/isUserSelect` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-E18C1FFEB32C` | 提交售后工单 | `/basicOpen/customerService/workOrder/auditFlow/summit` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-33F95EE20568` | 提交装箱信息 | `/amzStaServer/openapi/inbound-packing/setPackingInformation` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C4213C20454C` | 查询退款量（旧） | `/erp/sc/routing/finance/Refund/profitMonthRefund` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-7A722FDBD803` | Shopify-查询结算明细列表 | `/basicOpen/multiplatformFinance/shopify/bill/statement/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-234DAD222FC6` | 批量获取Listing费用 | `/listing/listing/open/api/listing/getPrices` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-EDBF02E1804D` | 查询库存分类账detail数据 | `/cost/center/ods/detail/query` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-790E7E6AB9BB` | 查询库存分类账summary数据 | `/cost/center/ods/summary/query` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-103335CE5263` | Temu全托-EPR费用 | `/basicOpen/multiplatformFinance/temuFull/epr/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-69D5B06BDFF5` | Temu全托-交易结算 | `/basicOpen/multiplatformFinance/temuFull/transaction/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-3283AED22A62` | Temu全托-仓储综合服务费 | `/basicOpen/multiplatformFinance/temuFull/warehouse/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A10D91D5AB63` | Temu全托-支出详情 | `/basicOpen/multiplatformFinance/temuFull/fee/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A65DD19702C9` | Temu全托-账务明细 | `/basicOpen/multiplatformFinance/temuFull/finance/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-3F89A847A787` | Temu半托-PO明细 | `/basicOpen/multiplatformFinance/temuHalf/po/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E3D81C603726` | Temu半托-其他账务 | `/basicOpen/multiplatformFinance/temuHalf/other/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-B837A02FDE37` | Temu半托-支出详情 | `/basicOpen/multiplatformFinance/temuHalf/fee/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-12361C6AC487` | Temu半托-账务明细 | `/basicOpen/multiplatformFinance/temuHalf/finance/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2C2C98986F8E` | Temu本土-账务明细 | `/basicOpen/multiplatformFinance/temuLocal/bill/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-9FB2983C3CFC` | TikTok账单明细 | `/basicOpen/multiplatformFinance/tiktokBill/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-F6D9634317AF` | VC报表-产品利润率报表 | `/basicOpen/vc/report/nppm/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-4A130F7050E6` | 回款明细-LazadaPayout | `/basicOpen/finance/lazada/payout/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-12A2A67A207B` | 回款明细-ShopeePayout | `/basicOpen/finance/shopee/payout/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-5FFDA0EB7172` | 查询FBA成本计价流水 | `/cost/center/api/cost/stream` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-DE9D2EFB4D37` | 查询Shein代运营回款明细列表 | `/basicOpen/multiplatformFinance/shein/full-managed/payout/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C50BE3C80987` | 查询Shein代运营收支明细列表 | `/basicOpen/multiplatformFinance/sheinFullManaged/salesSettlement/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-1AEABDB5A416` | 查询Shein代运营补扣款明细列表 | `/basicOpen/multiplatformFinance/shein/full-managed/adjustment-settlement/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-DD8358220FF8` | 查询利润报表-ASIN | `/bd/profit/report/open/report/asin/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-1508CACCC55B` | 查询利润报表-MSKU | `/bd/profit/report/open/report/msku/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-836E011F05F7` | 查询利润报表-父ASIN | `/bd/profit/report/open/report/parent/asin/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-067CAC8E94C1` | 查询利润统计-ASIN | `/bd/profit/statistics/open/asin/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D391B0E9A207` | 查询利润统计-父ASIN | `/bd/profit/statistics/open/parent/asin/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C6759B059E67` | 查询汇率 | `/erp/sc/routing/finance/currency/currencyMonth` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-29D1971BB402` | 查询结算中心 - 交易明细 | `/bd/sp/api/open/settlement/transaction/detail/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-0FFECA57D294` | 查询结算中心 - 结算汇总 | `/bd/sp/api/open/settlement/summary/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D797CA8C373A` | 立即重算-利润报表数据 | `/bd/profit/report/open/report/settle/compute/manual` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `side_effect_endpoint; not eligible for read-only sync PRP; requires separate owner approval if ever needed` |
| `LX-81629DDA1B88` | 美客多账单明细 | `/basicOpen/multiplatformFinance/mercado/bill/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-61CA08C2A0B0` | 账单明细-LazadaSettlement | `/basicOpen/finance/lazada/settlement/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-9BC7C0FC1FF2` | 账单明细-ShopeeAdjustment | `/basicOpen/finance/shopee/adjustment/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-7A37661DCA50` | 账单明细-ShopeeIncome | `/basicOpen/finance/shopee/income/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-EE2593BAC4F5` | FBM物流对账-确认/批量确认 | `/basicOpen/logistics/logisticsBill/confirm` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-F9E744EBA863` | Temu半托-发货面单费 | `/basicOpen/multiplatformFinance/temuHalf/ship/fee/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-6EA203F42077` | 作废费用单 | `/bd/fee/management/open/feeManagement/otherFee/discard` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-7ED46019A235` | 创建费用单 | `/bd/fee/management/open/feeManagement/otherFee/create` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-1E89A7A2DA3C` | 删除费用单 | `/bd/fee/management/open/feeManagement/otherFee/delete` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-A0706D312540` | 查询发货结算报告 | `/cost/center/api/settlement/report` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-20735537E141` | 编辑费用单 | `/bd/fee/management/open/feeManagement/otherFee/edit` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-D3A5B6A994C9` | 查询利润报表（旧） - ASIN（子级） | `/erp/sc/routing/finance/ProfitState/profitAsinSon` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-3D57A52589E7` | 查询利润报表（旧） - ASIN（父级） | `/erp/sc/routing/finance/ProfitState/profitAsin` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C7469949AF25` | VC报表-库存报表 | `/basicOpen/vc/report/inventory/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-EED28B643827` | 多平台-查询Coupang库存 | `/basicOpen/multiplatform/coupang/stockSearch` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-0A3640E4803A` | 多平台-查询FBS库存 | `/basicOpen/multiplatform/fbs/stockSearch` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-CB2AA7F5DD72` | 多平台-查询FBT库存 | `/basicOpen/multiplatform/fbt/stockSearch/v2` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-754101458F29` | 多平台-查询wayfair库存 | `/basicOpen/multiplatform/wayfair/stockSearch` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-7267D332382D` | 库存报表-FBA-历史报表-汇总-明细 | `/erp/sc/routing/fba/fbaStockReport/getList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2ED2F6B3D698` | 库存报表-FBA-新版-明细 | `/cost/center/openApi/fba/detail/query` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-97BF8DB332A5` | 库存报表-FBA-新版-汇总 | `/cost/center/openApi/fba/gather/query` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-647D3B813478` | 按ASIN查询FBA补货建议图表 | `/erp/sc/routing/fbaSug/asin/getDailySalesInfoFeature` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-10AEF8B863DC` | 按MSKU查询FBA补货建议图表 | `/erp/sc/routing/fbaSug/msku/getDailySalesInfoFeature` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D669477A844A` | 查询FBA库存列表 | `/erp/sc/routing/fba/fbaStock/fbaList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-52EB7C94DD2E` | 查询FBA库存列表-v2 | `/basicOpen/openapi/storage/fbaWarehouseDetail` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-220615AFB318` | 查询FBC平台仓信息 | `/basicOpen/openapi/fbc/stockSearch` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-B12AC94A93F3` | 查询FULL库存 | `/basicOpen/multiplatform/full/stockSearch` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-FB4EA16F878B` | 查询Temu平台仓备货单列表 | `/basicOpen/stockOrder/temu/queryPage` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-88185DB81F58` | 查询Temu库存 | `/basicOpen/multiplatform/fbt/stockSearch` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2F6DEEBA27AE` | 查询亚马逊源报表-FBA可售库存 | `/erp/sc/data/mws_report/getAfnFulfillableQuantity` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-FAD313A316C6` | 查询亚马逊源报表-FBA库存 | `/erp/sc/data/mws_report/manageInventory` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C665F51291FD` | 查询亚马逊源报表-每日库存 | `/erp/sc/data/mws_report/dailyInventory` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-6C3BA086A3D0` | 查询亚马逊源报表-预留库存 | `/erp/sc/data/mws_report/reservedInventory` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-FB5A5A1C2113` | 查询亚马逊源报表——Inventory Event Detail | `/erp/sc/data/mws_report/getFbaInventoryEventDetailList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2FC0FB186F97` | 查询亚马逊源报表—库龄表 | `/erp/sc/routing/fba/fbaStock/getFbaAgeList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-326AAA5EA5C0` | 查询亚马逊源表数据--Inventory Event Detail v1 | `/erp/sc/data/mws_report_v1/getFbaInventoryEventDetailList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E7E783692504` | 查询报表型数据明细-ASIN | `/erp/sc/routing/fbaSug/asin/getSourceList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2D6D0BBDF459` | 查询报表型数据明细-MSKU | `/erp/sc/routing/fbaSug/msku/getSourceList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-B6632DFC6552` | FBA仓发货计划释放库存 | `/basicOpen/openapi/fba/releaseStorage` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-FBD38287D8DA` | FBA仓发货计划锁库存 | `/basicOpen/openapi/fba/allocateStorage` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-7B4BDD7828CB` | Shein修改库存 | `/basicOpen/multiplatform/shein/createPublishQueue` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-F5534CBF1947` | Temu修改库存 | `/basicOpen/multiplatform/temu/createPublishQueue` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-6476F601BDF1` | Walmart修改库存 | `/basicOpen/multiplatform/walmart/publishQueue` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-E1A734FC8376` | 修改 FBM库存&处理时间 | `/basicOpen/FbmManagement/modifyFbmInventory` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-5C1C08254572` | 创建加工单 / 拆分单 | `/erp/sc/routing/inventoryReceipt/StorageProcess/addStorageProcessOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-8F4BA5E003C6` | 创建已完成的SKU调整单 | `/erp/sc/routing/inventoryReceipt/StorageAdjustment/addSkuAdjustmentOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-1FA55392B264` | 创建已完成的成本补录单 | `/erp/sc/routing/inventoryReceipt/CostChangeOrder/finishCostChangeOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-A054BADFE10F` | 创建已完成的换标调整单 | `/erp/sc/routing/inventoryReceipt/StorageAdjustment/addRebrandAdjustmentOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-E6238EC4E51A` | 创建已完成的数量调整单 | `/erp/sc/routing/inventoryReceipt/StorageAdjustment/addAdjustmentOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-2D7501EFFF14` | 创建已完成的盘点单 | `/erp/sc/routing/inventoryReceipt/InventoryCheck/addOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-41BB2D2886D2` | 创建待收货/已完成的调拨单 | `/erp/sc/routing/inventoryReceipt/StorageAllocation/addAllocationOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-5EBF326CAE51` | 创建待调拨的调拨单 | `/erp/sc/routing/inventoryReceipt/StorageAllocation/submitAllocationOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-9AE1466FB085` | 删除备货单 | `/basicOpen/overSeaWarehouse/stockOrder/delete` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-E4F62AF71863` | 平台仓发货单分配库存 | `/basicOpen/multiplatform/allocate/stock` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-3B84A6C4C9B4` | 海外仓备货单发货 | `/erp/sc/routing/owms/inbound/sendInbound` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-B6250EFFD833` | 添加入库单 | `/erp/sc/routing/storage/storage/orderAdd` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-FEFC2C739C57` | 添加出库单 | `/erp/sc/routing/storage/storage/orderAddOut` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-E8270027E4C1` | 备货单分配库存 | `/basicOpen/overSeaWarehouse/stockOrder/allocate` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-A6E36DA67F9C` | 调拨单全部收货 | `/erp/sc/routing/inventoryReceipt/StorageAllocation/receiveAllocationOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-C59B5D5BB158` | 调拨单分批收货 | `/erp/sc/routing/inventoryReceipt/StorageAllocation/partlyReceiveAllocationOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-375342860CAD` | 调拨单结束到货 | `/erp/sc/routing/inventoryReceipt/StorageAllocation/finishReceiveAllocationOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-0CF22467375C` | 创建UPC编码 | `/listing/publish/api/upc/addCommodityCode` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-C3A91E5872F8` | VC报表-流量报表 | `/basicOpen/vc/report/traffic/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A5A268931A5E` | 报告导出 - 报告下载链接续期 | `/basicOpen/report/amazonReportExportTask` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-61E78101B1CA` | 报告导出-查询导出任务结果 | `/basicOpen/report/query/reportExportTask` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2FC431E25099` | 查询IPI信息 | `/erp/sc/routing/fbaLimit/restock/getIpiInfo` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-00C35C824841` | 查询亚马逊国家下地区列表 | `/erp/sc/data/worldState/lists` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C4CB3335310B` | 查询亚马逊源报表-交易明细 | `/erp/sc/data/mws_report/transaction` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-02A75E695712` | 查询亚马逊源报表-盘存记录 | `/basicOpen/openapi/mwsReport/adjustmentList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-3FFAF18CCAEF` | 查询亚马逊赔偿报告列表 | `/basicOpen/openapi/mwsReport/reimbursementList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-FDCFE7F2A098` | 查询建议信息-ASIN | `/erp/sc/routing/fbaSug/asin/getInfo` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-DDA5705ED9EA` | 查询补货列表 | `/erp/sc/routing/restocking/analysis/getSummaryList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-12841C784119` | 查询补货限制列表 | `/basicOpen/openapi/replenishmentRestriction/page/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-EDBDC061B22F` | 查询规则 - ASIN | `/erp/sc/routing/fbaSug/asin/getConfig` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-93C1FB831AAA` | 查询运营日志 | `/basicOpen/operateManage/operateLog/list` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-8F98CEB43A6D` | 查询运营日志(新) | `/basicOpen/operateManage/operateLog/list/v2` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-EC7DBB7862BD` | VC发货单-确认发货 | `/basicOpen/openapi/getInvoice/invoice/batchSendGoods` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-0BAC0252E36F` | 作废采购单 | `/erp/sc/routing/purchase/purchase/cancel` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-78F82D8A146C` | 作废采购计划 | `/basicOpen/purchase/planCancel` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-99132180876E` | 修改我的汇率 | `/basicOpen/settings/exchangeRate/update` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-A4E9258A3B23` | 创建待采购的采购计划 | `/erp/sc/routing/data/local_inventory/createPurchasePlan` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-7A8CF9DA594A` | 创建报告 | `/openReport/report/task/createReport` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-A263B195A5CB` | 单个设置规则-ASIN | `/erp/sc/routing/fbaSug/asin/setConfig` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-6D84E6D8DCE8` | 批量设置规则 - ASIN | `/erp/sc/routing/fbaSug/asin/setConfigs` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-9BF0C09F6E66` | 报告导出 - 创建导出任务 | `/basicOpen/report/create/reportExportTask` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-86C8BA75BA4C` | 查询VC发货单列表 | `/basicOpen/openapi/getInvoice/page/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-3BF1A3763CCE` | 查询VC发货单详情 | `/basicOpen/openapi/getInvoice/detail` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-09D9FC0B390B` | 编辑采购计划备注（批量） | `/basicOpen/purchase/planModifyRemark` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-D4AEBED1B7C5` | 负责人维度-删除目标 | `/bd/goal/management/open/user/batchDelete` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-81721F0D55C3` | 负责人维度-新增/更新目标 | `/bd/goal/management/open/user/batchOperate` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-07FB91F93A00` | 查询产品表现 | `/bd/productPerformance/openApi/asinList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-7D9505D63FEB` | 查询建议信息-MSKU | `/erp/sc/routing/fbaSug/msku/getInfo` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-6D538A2534F5` | 查询规则 - MSKU | `/erp/sc/routing/fbaSug/msku/getConfig` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-F6890246F185` | 创建产品标签 | `/label/operation/v1/label/product/create` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-147DA91911E3` | 删除产品标签 | `/label/operation/v1/label/product/unmarkLabel` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-E9A089D7A679` | 单个设置规则-MSKU | `/erp/sc/routing/fbaSug/msku/setConfig` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-8682BCB2E674` | 批量设置规则 - MSKU | `/erp/sc/routing/fbaSug/msku/setConfigs` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2046A9CB4520` | 标记产品标签 | `/label/operation/v1/label/product/mark` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-90CFB48DDD46` | 产品启用、禁用 | `/basicOpen/product/productManager/product/operate/batch` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-D193FFF9539F` | 刊登管理-查询刊登结果 | `/listing/publish/openapi/amazon/product/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-23D1D18A4827` | 查询VC-Listing列表 | `/basicOpen/listingManage/vcListing/pageList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-03C994177272` | 查询VC订单列表 | `/basicOpen/platformOrder/vcOrder/pageList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-9D753B291919` | 查询VC订单详情【DF】 | `/basicOpen/platformOrder/vcOrderDf/detail` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-4CABE0BC0700` | 查询VC订单详情【PO】 | `/basicOpen/platformOrder/vcOrderPo/detail` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-B455B00EA7B8` | 查询亚马逊Listing | `/erp/sc/data/mws/listing` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-B8EB457780F2` | 查询亚马逊多渠道订单列表-v2 | `/order/amzod/api/orderList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A225E1E678EF` | 查询亚马逊源报表-FBA换货订单 | `/erp/sc/routing/data/order/fbaExchangeOrderList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-81A02022C253` | 查询亚马逊源报表-所有订单 | `/erp/sc/data/mws_report/allOrders` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E63338D86135` | 查询亚马逊源报表-移除订单（新） | `/erp/sc/routing/data/order/removalOrderListNew` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-B095F755E401` | 查询亚马逊订单列表 | `/erp/sc/data/mws/orders` | `old-system/source/docs/lingxing/Orderlists.md` | Yes | Yes | `DELETED` | No | `DELETED` |
| `LX-543268311F9C` | 查询亚马逊订单详情 | `/erp/sc/data/mws/orderDetail` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-7A3AB5828B68` | 查询亚马逊销量统计 | `/erp/sc/data/sales_report/asinDailyLists` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-71639106AB00` | 查询已有商品信息 | `/listing/publish/openapi/amazon/product/search` | `old-system/source/docs/lingxing/QueryProductList.md` | Yes | Yes | `DELETED` | No | `DELETED` |
| `LX-561EC879C9F0` | VC报表-实时销量报表 | `/basicOpen/vc/report/realtimeSales/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-918F82FAAD56` | VC报表-销量报表 | `/basicOpen/vc/report/sales/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D8AC40C34CC3` | 刊登管理-查询 Amazon 子分类 | `/basicOpen/openapi/publish/manage/categoryChildren` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-5C949B5E2033` | 刊登管理-查询 Amazon 根分类 | `/basicOpen/openapi/publish/manage/categoryRoot` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A1B412C86753` | 查询亚马逊标发结果 | `/pb/mp/order/getFulfillmentResult` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2077895D6B9A` | Listing删除商品标签 | `/basicOpen/listingManage/removeListingAndTag` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-7D621DDB5AD5` | SC订单-设置订单备注 | `/basicOpen/platformOrder/scOrder/setRemark` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-E1F320E3A8B9` | 亚马逊订单提交标发 | `/pb/mp/order/submitFulfillment` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-76CFCB697A50` | 修改B2B价格 | `/basicOpen/b2bPrice/modifyPrice` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-34F6AE02AF12` | 刊登管理-提交商品资料 | `/listing/publish/openapi/amazon/product/publish` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-53CEF6E794BE` | 创建亚马逊多渠道订单 | `/order/amzod/api/createOrder` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D58D9CF7D14C` | 创建已完成的采购变更单 | `/erp/sc/routing/purchase/purchaseChangeOrder/createPurchaseChangeOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-4674779EEB39` | 创建待到货的采购单 | `/erp/sc/routing/purchase/purchase/createPurchaseOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-F8006AE8F077` | 创建移除订单 | `/erp/sc/statistic/removalOrder/createAndCommit` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-1D4F82B9EC6C` | 创建订单 | `/pb/mp/order/v2/create` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-06BDDD3B9762` | 删除Listing标签 | `/basicOpen/globalTag/listing/removeTag` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-ED103184FB35` | 取消多渠道订单 | `/order/amzod/api/cancelOrder` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D0A92205A559` | 审核发货 | `/basicOpen/openapi/multiplatform/order/review` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-A96852EA632C` | 批量修改Listing价格 | `/erp/sc/listing/ProductPricing/pricingSubmit` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-D2402601914F` | 批量编辑本地信息 | `/basicOpen/product/editOnSaleTimeAndRemark` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-80C0100C2D4F` | 查询Listing标记标签列表 | `/basicOpen/listingManage/queryListingRelationTagList` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-42B55A79C3D8` | 查询亚马逊自发货订单列表 | `/erp/sc/routing/order/Order/getOrderList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E42C58B6D66A` | 查询亚马逊自发货订单详情 | `/erp/sc/routing/order/Order/getOrderDetail` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-25313630C917` | 标记订单不发货 | `/pb/mp/order/v2/cancelOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-1C246F17173F` | 添加Listing标签 | `/basicOpen/globalTag/listing/addTag` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-DCEB8C231969` | 编辑/更新自发货订单 | `/pb/mp/order/v2/updateOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-3BAA5CBA09DF` | 编辑订单 | `/pb/mp/order/editOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-5CD66DB6C0A0` | 编辑采购单备注 | `/basicOpen/purchase/orderModifyRemark` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-DA41D6369A41` | 解除Listing配对 | `/basicOpen/listingManage/unLinkListingPairs` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-0C5785F744AB` | 配对/批量配对 | `/basicOpen/vcservice/productRelation/batchLink` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-583232734D6F` | 采购单下单 | `/erp/sc/routing/purchase/purchase/setOrders` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-C037C9690479` | FBA费差异-异常订单-MSKU | `/basicOpen/openapi/sale/fbaFeeDifference/msku/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E6BDA4FE4C76` | FBA费差异-异常订单-订单 | `/basicOpen/openapi/sale/fbaFeeDifference/order/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C79145A7BD7A` | Listing新增商品标签 | `/basicOpen/listingManage/bindListingAndTag` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-8198E3740745` | VC订单-打印标签【DF】 | `/basicOpen/platformOrder/vcOrderDf/getShippingLabel` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-8DC9ADC8B0DC` | VC订单-请求标签【DF】 | `/basicOpen/platformOrder/vcOrderDf/submitShippingLabel` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-B6C99BAA3905` | 合并订单 | `/pb/mp/order/v2/mergeOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `side_effect_endpoint; not eligible for read-only sync PRP; requires separate owner approval if ever needed` |
| `LX-C7F36F028E66` | 批量分配Listing负责人 | `/listing/listing/open/api/asin/updatePrincipal` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-F05BAD345036` | 拆分订单 | `/pb/mp/order/v2/splitOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `side_effect_endpoint; not eligible for read-only sync PRP; requires separate owner approval if ever needed` |
| `LX-D620C03B7D98` | 查询亚马逊源报表-移除订单（旧） | `/erp/sc/data/mws_report/removalOrders` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-F25F4D4BC4A3` | 查询产品表现（旧） | `/erp/sc/data/sales_report/asinList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-715956D8FA89` | 订单称重 | `/erp/sc/routing/wms/order/setOrderWeighed` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `side_effect_endpoint; not eligible for read-only sync PRP; requires separate owner approval if ever needed` |
| `LX-500C4287A05E` | 采购单整单结束到货 | `/basicOpen/purchase/setOrderFinish` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-9FB86E3706A3` | 多平台-查询Line在线商品 | `/basicOpen/multiplatform/line/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-CC803C771DAC` | 查询AliExpress在线商品 - 托管模式 | `/basicOpen/multiplatform/aliexpress/list/v2` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-142817E5A1DF` | 查询AliExpress在线商品 - 自运营 | `/basicOpen/multiplatform/aliExpress/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-968880024AAB` | 查询Cdiscount在线商品 | `/basicOpen/multiplatform/cdiscount/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-67040FDD5156` | 查询Coupang在线商品 | `/basicOpen/multiplatform/coupang/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-5E8A58876154` | 查询Kaufland在线商品 | `/basicOpen/multiplatform/kaufland/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-7748876702DC` | 查询Lazada在线商品 | `/basicOpen/multiplatform/lazada/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2EDE180FD7FA` | 查询Mercado在线商品 | `/basicOpen/multiplatform/mercado/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-9D6543F69CD3` | 查询OTTO在线商品 | `/basicOpen/multiplatform/otto/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-1F44B7286A72` | 查询Ozon在线商品 | `/basicOpen/multiplatform/ozon/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D18D1C8DA325` | 查询Qoo10在线商品 | `/basicOpen/multiplatform/qoo10/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-56E907397A06` | 查询Rakuten在线商品 | `/basicOpen/multiplatform/rakuten/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-CF719815C975` | 查询Shein在线商品 | `/basicOpen/multiplatform/shein/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-289F49946DB5` | 查询Shopee在线商品 | `/basicOpen/multiplatform/shopee/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-6C1D3D754AFF` | 查询Shopify在线商品 | `/basicOpen/multiplatform/shopify/variantList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C32514EE9F0F` | 查询Temu在线商品 | `/basicOpen/multiplatform/temu/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-EF9C7419BD40` | 查询TikTok产品表现 | `/basicOpen/platformStatistics/tiktokProductAnalysis/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-19C74D2BC60E` | 查询TikTok在线商品 | `/basicOpen/multiplatform/tiktok/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-492FEC842AE2` | 查询eBay在线商品列表 | `/basicOpen/multiplatform/ebay/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-F82986F65A5D` | 查询亚马逊店铺列表 | `/erp/sc/data/seller/lists` | `old-system/source/docs/lingxing/SellerLists.md` | No | Yes | `DELETED` | No | `DELETED` |
| `LX-C97AA42C1456` | 查询亚马逊概念店铺列表 | `/erp/sc/data/seller/conceptLists` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-21FC8634582C` | 查询阿里国际站在线商品 | `/basicOpen/multiplatform/alibaba/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-4500576F2B8E` | 查询亚马逊市场列表 | `/erp/sc/data/seller/allMarketplace` | `old-system/source/docs/lingxing/AllMarketplace.md` | No | Yes | `DELETED` | No | `DELETED` |
| `LX-65E684431831` | 店铺维度-删除目标 | `/bd/goal/management/open/store/batchDelete` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-1BE23A99A7E9` | 批量修改店铺名称 | `/erp/sc/data/seller/batchEditSellerName` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-9A6E1D56E418` | 批量添加、编辑多平台配对关系 | `/pb/mp/listing/v2/pairMultiPlatform` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-2C3EA8AD49D5` | 查询多平台配对列表 | `/pb/mp/listing/v2/getPairList` | `old-system/source/docs/lingxing/PairListV2.md` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-532ADAD560E1` | 店铺维度-新增/更新目标 | `/bd/goal/management/open/store/batchOperate` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-19A4815CBA6E` | 批量TEMU地址解密 | `/basicOpen/temu/temuAddressDecrypt` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-9CD190638C17` | 查询AWD入库任务列表 | `/amzStaServer/openapi/awd/inbound-plan/page` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C2390BB79F75` | 查询AWD入库任务详情 | `/amzStaServer/openapi/awd/inbound-plan/detail` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-36B9E5516331` | 查询AWD入库货件列表 | `/amzStaServer/openapi/awd/inbound-shipment/page` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-21427E079EB6` | 查询AWD入库货件详情 | `/amzStaServer/openapi/awd/inbound-shipment/detail` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C41B32188946` | 查询FBA到货接收明细 | `/erp/sc/data/fba_report/receivedInventory` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-8A3BEF320B33` | 查询FBA商品信息列表 | `/erp/sc/routing/fba/shipment/getFbaProductList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-CEDC59ED8563` | 查询FBA货件商品FNSKU标签 | `/erp/sc/storage/shipment/printFnskuLabels` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-676C983961A2` | 查询亚马逊源报表-FBA订单 | `/erp/sc/data/mws_report/fbaOrders` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-4B9473A2D2E1` | 查询收货单列表 | `/erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/getOrderList` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-ECAEE8038F87` | 查询质检单列表 | `/erp/sc/routing/deliveryReceipt/ReceiptOrderQc/getOrderList` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-A49B65E222D2` | 获取商品预处理信息 | `/amzStaServer/openapi/inbound-packing/getPrepDetails` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-EE7D15BC8C4F` | 装箱任务-单据列表 | `/basicOpen/packingTask/getRelateSnList` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-A25AE6134CEB` | 地址簿-配送地址详情 | `/basicOpen/openapi/fbaShipment/shoppingAddress` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-21F5B3DD122D` | 查询FBA月仓储费 | `/erp/sc/data/fba_report/storageFeeMonth` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-0D1D1ECB7280` | 查询FBA货件箱子、卡板标签 | `/erp/sc/storage/shipment/printFbaLabels` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-F383D3B7EB6F` | 查询FBA长期仓储费 | `/erp/sc/data/fba_report/storageFeeLongTerm` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-BCC0B20A9D59` | 查询FBT货件列表 | `/basicOpen/fbtShipment/cargo/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-156A1CB27E37` | 查询STA任务列表 | `/amzStaServer/openapi/inbound-plan/page` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-0729C772C5E1` | 查询STA任务详情 | `/amzStaServer/openapi/inbound-plan/detail` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-20EB3FCA79C6` | 查询Temu货件 | `/basicOpen/multiplatform/temu/cargo` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-DC338785A675` | 查询亚马逊源报表-移除货件（新） | `/erp/sc/statistic/removalShipment/list` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-974EFCEA0C56` | 查询亚马逊源报表—Amazon Fulfilled Shipments | `/erp/sc/data/mws_report/getAmazonFulfilledShipmentsList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D501F92C7758` | 查询亚马逊源报表—Amazon Fulfilled Shipments v1 | `/erp/sc/data/mws_report_v1/getAmazonFulfilledShipmentsList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-184082D0A5CE` | 查询包装组 | `/amzStaServer/openapi/inbound-packing/listPackingGroupItems` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-4B23C6732DA7` | 查询可选送达时间 | `/amzStaServer/openapi/inbound-shipment/getDeliveryDateList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-FC05687554B2` | 查询异步任务状态 | `/amzStaServer/openapi/task-plan/operate` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-07046A9822CD` | 查询承运方式 | `/amzStaServer/openapi/inbound-shipment/getTransportList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2A6240555EDE` | 查询货件列表 | `/erp/sc/data/fba_report/shipmentList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-F5A7C6E4E488` | 查询货件方案 | `/amzStaServer/openapi/inbound-shipment/shipmentPreView` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-DCE1920441EE` | 查询货件方案的装箱信息 | `/amzStaServer/openapi/inbound-packing/getInboundPackingBoxInfo` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-066D1637AD45` | 查询货件装箱信息 | `/amzStaServer/openapi/inbound-shipment/listShipmentBoxes` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-9761AD3B5D67` | 查询货件装箱信息 | `/erp/sc/routing/fba/shipment/boxInfo` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-89CF383FDABC` | 查询货件详情 | `/amzStaServer/openapi/inbound-shipment/shipmentDetailList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-0D638DE6BBFF` | FBA-作废发货单 | `/basicOpen/openapi/fbaShipment/shipmentSn/invalid` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-020A16FE03E9` | FBA发货单发货 | `/erp/sc/storage/shipment/sendGoods` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-4722725D540A` | VC订单-确认发货【DF】 | `/basicOpen/platformOrder/vcOrderDf/confirmShipment` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D8BC30F67A4B` | 上传备货单装箱信息 | `/erp/sc/routing/owms/inbound/packing` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-927D66FB6D5A` | 上传本地产品图片 | `/erp/sc/routing/storage/product/uploadPictures` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-C652E548D8E6` | 上传货件跟踪号 | `/amzStaServer/openapi/inbound-shipment/updateShipmentTrack` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-A8AF20B777AE` | 修改平台仓发货单备注 | `/cepf/warehouse/api/openApi/editPlatfromShippingRemark` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-AB8C08F7A8A1` | 修改货件实际状态 | `/erp/sc/routing/storage/shipment/updateShipmentActualStatus` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-FDE4D2E54607` | 修改货件装箱信息 | `/amzStaServer/openapi/inbound-packing/updateShipmentPacking` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-F395006EFE91` | 入库单确认入库 | `/basicOpen/inboundOrder/inbound/setInbound` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-02B0DCBC4860` | 出库单确认出库 | `/basicOpen/outboundOrder/outbound/setOutbound` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-9B1ADE54CD39` | 创建AWD入库任务 | `/amzStaServer/openapi/awd/inbound-plan/createInboundPlan` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-655FA8E41C1A` | 创建FBA发货计划 | `/erp/sc/routing/storage/shipment/createShipmentPlan` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-5567B5700B78` | 创建待发货/待收货/已完成的备货单 | `/erp/sc/routing/owms/inbound/createInbound` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-AA0068524F96` | 创建待收货的收货单 | `/erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/createReceiptOrder` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-ECC5B6E072BC` | 删除出库单 | `/basicOpen/outboundOrder/outbound/delete` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-6E971E9E2A37` | 删除发货单 | `/basicOpen/openapi/fbaShipment/deleteShipmentList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-72F91B3597A5` | 删除暂存货件 | `/basicOpen/multiplatform/deleteCargoStorage` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-C8A51960BF37` | 发货单分配库存 | `/erp/sc/routing/storage/shipment/lockStock` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-1E7F3D661CD9` | 发货单创建接口结果查询 | `/erp/sc/routing/storage/shipment/searchProcessResult` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-336EA1296121` | 发货单释放库存 | `/erp/sc/routing/storage/shipment/releaseStock` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-59FEBA8976F8` | 取消AWD入库任务 | `/amzStaServer/openapi/awd/inbound-plan/cancel` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-6C5A07CE219D` | 取消STA任务 | `/amzStaServer/openapi/inbound-plan/cancelInboundPlan` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-BA2172D4AF5C` | 同步STA任务到ERP | `/amzStaServer/openapi/inbound-plan/gatherInboundPlan` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-D0E5ED75F09D` | 同步亚马逊货件到ERP | `/erp/sc/routing/fba/shipment/syncShipment` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-9319A5A1B49B` | 地址簿-发货地址修改 | `/erp/sc/routing/fba/shipment/updateShipFromAddress` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-97436D0F6DE3` | 地址簿-发货地址列表 | `/erp/sc/routing/fba/shipment/shipFromAddressList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-F4ECA85B0BF7` | 地址簿-发货地址创建 | `/erp/sc/routing/fba/shipment/createShipFromAddress` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-0EF3921B4688` | 平台仓发货单发货 | `/basicOpen/multiplatform/shippingList/delivery` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-1AA8D77AEA04` | 平台仓发货单拣货 | `/basicOpen/multiplatform/shippingList/picking` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-8BA8E838E694` | 手动同步FBT货件 | `/basicOpen/fbtShipment/cargo/sync` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-5ED414F8B846` | 批量查询发货单详情 | `/erp/sc/routing/storage/shipment/getInboundShipmentListMwsDetailList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-04A6C56A7729` | 批量添加/编辑Listing配对 | `/erp/sc/storage/product/link` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-F83A1BAC3521` | 批量添加头程物流商 | `/erp/sc/routing/tms/FirstVessel/addProviders` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-AF600FDF4D6E` | 批量添加头程物流方式 | `/erp/sc/routing/tms/FirstVessel/addChannels` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-5B7707DD0B84` | 提交货件配送服务 | `/amzStaServer/openapi/inbound-shipment/setDeliveryService` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-FDB28F61C904` | 提交送达时间 | `/amzStaServer/openapi/inbound-shipment/commitStaDeliverTime` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-186837F0F7C4` | 收货单-编辑备注 | `/basicOpen/inboundOrder/receiptOrder/updateOrderInfo` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-45D95718F6DB` | 更新发货单物流信息 | `/erp/sc/routing/storage/shipment/updateListLogistics` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-7F4CD53DF3FB` | 更新发货单自定义成本 | `/erp/sc/routing/storage/shipment/updateCustomCost` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-30FE81602632` | 查询FBA发货计划 | `/erp/sc/data/fba_report/shipmentPlanLists` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-1074DDF41A1A` | 查询WFS货件可添加商品列表 | `/basicOpen/multiplatform/cargo/addCargoGoods/list` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-B6E739AA52D4` | 查询发货单列表 | `/erp/sc/routing/storage/shipment/getInboundShipmentList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-4EBAEE6FE781` | 查询发货单详情 | `/erp/sc/routing/storage/shipment/getInboundShipmentListMwsDetail` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-043952293C81` | 查询已启用的自发货物流方式 | `/erp/sc/routing/wms/WmsLogistics/listUsedLogisticsType` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-C99E2D00C76D` | 查询平台仓发货单列表 | `/cepf/warehouse/api/openApi/queryShippingListPage` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-9D5A176AC470` | 查询平台仓发货单列表v2 | `/basicOpen/multiplatform/query/shippingList` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-418571887440` | 查询平台仓发货单详情 | `/basicOpen/multiplatform/query/shippingDetail` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-87EAA59FF5C7` | 查询海外仓sku配对列表 | `/basicOpen/overseaWarehouseSetting/matchList` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-E726A7FC946C` | 查询调整单确认调整异步结果 | `/basicOpen/adjustOrder/adjust/getAdjustStatus` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-208BCCE30B24` | 海外仓sku取消配对 | `/basicOpen/overseaWarehouseSetting/productUnMatch` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-EECD62D39B8C` | 海外仓sku配对 | `/basicOpen/overseaWarehouseSetting/productMatch` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-A8BA6E5445AA` | 添加 / 编辑产品分类 | `/erp/sc/routing/storage/category/set` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-3B1AB09F56B1` | 添加 / 编辑产品属性 | `/erp/sc/routing/storage/attribute/set` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-1BDE9AFED615` | 添加 / 编辑捆绑产品 | `/erp/sc/routing/storage/product/setBundled` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-E5135AAB2CB9` | 添加 / 编辑辅料 | `/erp/sc/routing/storage/product/setAux` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-0C9F53813C1C` | 添加/修改仓库 | `/erp/sc/storage/wareHouse/edit` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-D181D27E9336` | 添加/修改供应商 | `/erp/sc/routing/storage/supplier/edit` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-E85460D3A0AD` | 添加/编辑产品品牌 | `/erp/sc/storage/brand/set` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-DC8F85A264F4` | 添加/编辑多属性产品 | `/erp/sc/routing/storage/spu/set` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-F00018116434` | 添加/编辑本地产品 | `/erp/sc/routing/storage/product/set` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-4C457588B444` | 添加仓位 | `/erp/sc/routing/storage/wareHouseBin/create` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-0B7D3781D062` | 添加采购单物流信息 | `/erp/sc/routing/purchase/purchase/addLogistics` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-A8841B7061A1` | 物流下单 - 编辑运单号/跟踪号 | `/basicOpen/logisticsOrdering/setTrackingNo` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-A39F9B3A3F04` | 生成已发货的发货单 | `/erp/sc/storage/shipment/createSendedOrder` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-7975BA4E29DD` | 生成待发货的发货单 | `/erp/sc/routing/storage/shipment/createReadySendOrder` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-BF8FCC06026C` | 确认AWD入库任务 | `/amzStaServer/openapi/awd/inbound-plan/confirmInboundPlan` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-E2A62AA24630` | 确认货件方案 | `/amzStaServer/openapi/inbound-shipment/confirmPlacementOption` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-F8B75D5777E4` | 编辑FBA发货计划 | `/erp/sc/routing/storage/shipment/updateShipmentPlan` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-C24E09A786AA` | 编辑发货单 | `/erp/sc/routing/storage/shipment/updateInboundShipmentListMws` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-961D3F6744BF` | 获取发货单头程物流信息-其他费类型 | `/erp/sc/routing/fba/shipment/getHeadLogisticsFeeTypes` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-914E18FBB348` | 获取发货单头程物流信息-承运商信息 | `/erp/sc/routing/fba/shipment/getSeaTrackSupplierCarriers` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-5094B5DD4252` | 装箱任务-删除装箱任务 | `/basicOpen/packingTask/delTask` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-9B0AEF588990` | 装箱任务-批量编辑装箱信息 | `/basicOpen/packingTask/batchEditPackingBox` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-DBA03B840847` | 装箱任务-标记已完成 | `/basicOpen/packingTask/finishTask` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-3AE2636790C1` | 订单发货 | `/basicOpen/selfShipmentOrder/deliveryGoods` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-890B84A34002` | 设置包裹尺寸 | `/erp/sc/routing/wms/order/setOrderPackageSize` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-24115FEF3839` | 调整单确认调整 | `/basicOpen/adjustOrder/adjust/setAdjust` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-06B2902A5005` | 预发货 | `/basicOpen/openapi/multiplatform/order/preShipment` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-3A4304922BAA` | WFS货件暂存 | `/basicOpen/multiplatform/cargo/storage` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-0A097BF31BAA` | 保存装箱信息 | `/amzStaServer/openapi/inbound-packing/setLocalPackingInformation` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-69795348C946` | 创建STA任务 | `/amzStaServer/openapi/inbound-plan/createInboundPlan` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-50E3A9271BE9` | 删除调拨单 | `/basicOpen/storageAllocationList/delete` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-A78F75179F06` | 启用、禁用仓位 | `/erp/sc/routing/storage/wareHouseBin/switchStatus` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-87182E99B1B7` | 备货单分批收货 | `/erp/sc/routing/owms/inbound/batchesReceipt` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-3E19FAF15A8D` | 备货单结束到货 | `/erp/sc/routing/owms/inbound/completeReceipt` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-8FB1CC9572F0` | 导入面单 | `/basicOpen/selfShipmentOrder/importLabel` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-B1D5E5BD6509` | 快速出库 | `/pb/mp/order/v2/fastOutbound` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-E136355F65BA` | 打印AWD入库货件箱子标签 | `/amzStaServer/openapi/awd/inbound-shipment/uploadPacking` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-032E4A4848FB` | 撤销入库单 | `/basicOpen/inboundOrder/inbound/setOrderRevoke` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-C0FCAFE34051` | 撤销出库单 | `/basicOpen/outboundOrder/outbound/setOrderRevoke` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-FC8B93582D77` | 撤销调拨单 | `/basicOpen/storageAllocationList/cancel` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-E8B767C41774` | 收货单到货 | `/erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/receive` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-FE893F657641` | 收货单快捷入库 | `/erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/fastReceive` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-4B7E0262DFD8` | 更新AWD入库任务 | `/amzStaServer/openapi/awd/inbound-plan/updateInboundPlan` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-8A0CC84D50E1` | 更新AWD货件跟踪编号 | `/amzStaServer/openapi/awd/inbound-shipment/updateShipmentInfo` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-01FE108B1B92` | 更新备货单 | `/erp/sc/routing/owms/inbound/updateInbound` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-25557AAD1424` | 更新备货单物流信息 | `/erp/sc/routing/owms/inbound/updateLogistics` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |
| `LX-24E61C09FB66` | 查询亚马逊源报表-移除货件（旧） | `/erp/sc/data/fba_report/removalLists` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-4D2673DB3C7D` | 生成可选送达时间 | `/amzStaServer/openapi/inbound-shipment/generateDeliveryDateList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-2E466DAF8EFF` | 生成承运方式 | `/amzStaServer/openapi/inbound-shipment/generateTransportList` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-1F00F24DFD68` | 生成货件方案 | `/amzStaServer/openapi/inbound-shipment/generatePlacementOptions` | `normalized CSV only` | No | No | `DELETED` | No | `DELETED` |
| `LX-633648A48963` | 装箱任务-生成装箱任务 | `/basicOpen/packingTask/addTask` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `side_effect_endpoint; not eligible for read-only sync PRP; requires separate owner approval if ever needed` |
| `LX-330811625C41` | 销售出库单截单 | `/basicOpen/wmsOrder/cancel` | `normalized CSV only` | Yes | Yes | `DO_NOT_USE` | No | `DO_NOT_USE` |

## Domain-level gaps

- WFS fee: no standalone provider endpoint contract was found in the allowed repository source set; keep `PROVIDER_CONTRACT_MISSING` and do not hard-code a fee.
- All retained interface verification rows are currently unverified. Structural completeness is not authentication, permission, scope, pagination, rate-limit, or production-readiness evidence.
- Entries with normalized-CSV-only evidence need an authoritative provider document or controlled evidence capture before transport implementation.
- Deleted and non-Walmart comparators remain historical evidence only.

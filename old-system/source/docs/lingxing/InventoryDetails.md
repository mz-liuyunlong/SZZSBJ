# 查询仓库库存明细
支持查询本地仓/海外仓库存明细，对应系统【仓库】>【库存明细】数据

## 接口信息

| API Path | 请求协议 | 请求方式 | [令牌桶容量](/docs/Guidance/newInstructions?id=_5-限流算法说明) |
| :------------ | :------------ | :------------ | :------------ |
| `/erp/sc/routing/data/local_inventory/inventoryDetails` | HTTPS | POST | 1 |

## 请求参数  

| 参数名  | 说明              | 必填 | 类型 | 示例 |
| :------------ |:----------------| :------------ | :------------ | :------------ |
|wid| 仓库id，多个使用英文逗号分隔 |否|[string]|1,578,765|
|offset| 分页偏移量，默认0       |否|[int]|0|
|length| 分页长度，默认20，上限800 |否|[int]|20|
|sku| SKU，单个,（模糊搜索）   |否|[string]|Test01|

## 请求示例
```
{
    "wid": "1,578,765",
    "offset": 0,
    "length": 20,
    "sku": "Test01"
}
```

## 返回结果
Json Object

| 参数名  | 说明 | 必填 | 类型 | 示例 |
| :------------ | :------------ | :------------ | :------------ | :------------ |
|code|状态码，0 成功|是|[int]|0|
|message|消息提示|是|[string]|success|
|error_details|错误信息|是|[array]|  |
|request_id|请求链路id|是|[string]|BD36FCD8-E32E-E9E1-6BEC-06DE331C95AB|
|response_time|响应时间|是|[string]|2021-06-15 17:49:16|
|total|总数|是|[int]|1|
|data|响应数据|是|[array]|  |
|data>>wid|仓库id|是|[int]|1771|
|data>>product_id|本地产品id|是|[int]|23551|
|data>>sku|SKU|是|[string]|sku-1|
|data>>seller_id|店铺id|是|[string]| |
|data>>fnsku|FNSKU|是|[string]| |
|data>>product_total|实际库存总量【可用量+次品量+待检待上架量+锁定量】|是|[int]|11|
|data>>product_valid_num|可用量|是|[int]|11|
|data>>expect_valid_num|期望可用|是|[int]|11|
|data>>product_bad_num|次品量|是|[int]| |
|data>>product_qc_num|待检待上架量|是|[int]| |
|data>>product_lock_num|锁定量|是|[int]| |
|data>>stock_cost_total|库存成本|是|[string]|11.00|
|data>>quantity_receive|待到货量|是|[string]|1|
|data>>expect_pending_num|期望待到货量|是|[int]|1|
|data>>stock_cost|单位库存成本|是|[string]|1.00|
|data>>product_onway|调拨在途|是|[int]|1|
|data>>transit_head_cost|调拨在途头程成本|是|[string]|0.01|
|data>>average_age|平均库龄|是|[int]|1|
|data>>third_inventory|海外仓第三方库存信息|是|[object]| |
|data>>third_inventory>>qty_sellable|可用量|是|[int]|35194|
|data>>third_inventory>>qty_pending|待上架库存|是|[int]| |
|data>>third_inventory>>qty_reserved|锁定量|是|[int]|7|
|data>>third_inventory>>qty_onway|第三方海外仓备货在途|是|[int]| |
|data>>third_inventory>>third_inventory_data|海外仓子产品库存明细|是|[array]| |
|data>>third_inventory>>third_inventory_data>>name|库存对比|是|[string]| |
|data>>third_inventory>>third_inventory_data>>local|系统|是|[int]| |
|data>>third_inventory>>third_inventory_data>>third|第三方仓|是|[int]| |
|data>>third_inventory>>third_inventory_data>>diff|库存差异|是|[int]| |
|data>>third_inventory>>third_inventory_data>>support_box|是否同步箱库存|是|[boolean]| |
|data>>third_inventory>>third_inventory_data>>product_third|(三方可用量-箱库存可用量 ) * 配对数量|是|[int]| |
|data>>third_inventory>>third_inventory_data>>box_third|箱库存可用量 * 配对数量|是|[int]| |
|data>>third_inventory>>third_inventory_data>>children|海外仓子项库存明细列表|是|[array]| |
|data>>third_inventory>>third_inventory_data>>children>>third_sku|海外仓sku|是|[string]| |
|data>>third_inventory>>third_inventory_data>>children>>third_name|海外仓sku名称|是|[string]| |
|data>>third_inventory>>third_inventory_data>>children>>match_num|配对数量|是|[int]| |
|data>>third_inventory>>third_inventory_data>>children>>third_value|三方可用量|是|[int]| |
|data>>third_inventory>>third_inventory_data>>children>>third_total_value|三方可用量*配对数量|是|[int]| |
|data>>third_inventory>>third_inventory_data>>children>>product_third|(三方可用量-箱库存可用量 ) * 配对数量|是|[int]| |
|data>>third_inventory>>third_inventory_data>>children>>box_third|箱库存可用量 * 配对数量|是|[int]| |
|data>>stock_age_list|库龄信息|是|[array]| |
|data>>stock_age_list>>name|标题|是|[string]|0-15天库龄|
|data>>stock_age_list>>qty|数量|是|[int]|1|
|data>>purchase_price|采购单价|是|[string]||
|data>>price|单位费用|是|[string]||
|data>>head_stock_price|单位头程|是|[string]||
|data>>stock_price|单位库存成本|是|[string]||

# 返回成功示例
```
{
    "code": 0,
    "message": "success",
    "error_details": [],
    "request_id": "B6566678-9238-338C-3FD5-BBEEF01635BA",
    "response_time": "2022-09-08 15:57:49",
    "data": [
        {
            "wid": 1,
            "product_id": 10001,
            "sku": "1111",
            "seller_id": "0",
            "fnsku": "",
            "product_total": 1943,
            "product_valid_num": 681,
            "expect_valid_num": 681,
            "product_bad_num": 110,
            "product_qc_num": 519,
            "product_lock_num": 633,
            "stock_cost_total": "19430.00",
            "quantity_receive": "562",
            "expect_pending_num": 562,
            "stock_cost": "10.0000",
            "product_onway": 0,
            "transit_head_cost": "0.00",
	        "average_age": 135,
            "third_inventory": [],
            "stock_age_list": [
                {
                    "name": "0-15天库龄",
                    "qty": 20
                },
                {
                    "name": "16-30天库龄",
                    "qty": 0
                },
                {
                    "name": "31-90天库龄",
                    "qty": 1348
                },
                {
                    "name": "91天以上库龄",
                    "qty": 575
                }
            ]
        }
    ],
    "total": 1
}
```
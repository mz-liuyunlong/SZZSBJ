# 查询多平台配对列表
获取多平台系统中【产品】>【配对列表】中数据已配对的数据。该模块数据为多平台MSKU与本地SKU的配对关系  

| API Path | 请求协议 | 请求方式 | [令牌桶容量](/docs/Guidance/newInstructions?id=_5-限流算法说明) |
| :------------ | :------------ | :------------ | :------------ |
| `/pb/mp/listing/v2/getPairList   ` | HTTPS | POST  | 10 |

## 请求参数

| 参数名 | 说明 | 必填 | 类型 | 示例 |
| :------------ | :------------ | :------------ | :------------ | :------------ |
|length|分页条数|否|[int]|20|
|offset|分页偏移量|否|[int]|0|
|msku|MSKU|否|[array]|["test0001","xzc002","custom001"]|
|sku|本地SKU|否|[array]|["Book-A4-60"]|
|start_time|操作开始时间，闭区间|否|[string]|2021-04-24 22:09:43|
|end_time|操作结束时间，开区间|否|[string]|2023-06-24 22:09:43|
|platform_codes|平台码|否|[array]|["10003","10010"]|
|store_ids|店铺id|否|[array]|["11084135313207808"]|
|use_cursor|分页游标，默认为fasle，如配对数据多时，强烈建议您使用分页游标的方式分页，可加快接口响应速度|否|[boolean]|true|
|cursor_id|游标id, 当分页游标为true时，该字段必填|否|[boolean]|true|

## 请求示例
```
{
    "offset": 0,
    "length": 20,
    "msku": [
        "test0001",
        "xzc002",
        "custom001"
    ],
    "sku": [
        "Book-A4-60"
    ],
    "start_time": "2021-04-24 22:09:43",
    "end_time": "2023-06-24 22:09:43",
    "platform_codes": [
        "10003",
        "10010"
    ],
    "store_ids": [
        "11084135313207808"
    ]
}
```

## 返回结果
Json Object

| 参数名 | 说明 | 必填 | 类型 | 示例 |
| :------------ | :------------ | :------------ | :------------ | :------------ |
|code|状态码，0 成功|是|[int]|0|
|message|提示信息|是|[string]|操作成功|
|request_id|请求链路id|是|[string]|1e76129e-c622-420f-852e-08262755cfcc.1721705863164|
|response_time|响应时间|是|[string]|2024-07-23 11:37:43|
|data|响应数据|是|[array]| |
|data>>total|总数，当不使用分页游标方式时返回|否|[number]|1|
|data>>has_next|是否存在下一页，当使用分页游标方式时返回|否|[boolean]|1|
|data>>next_cursor_id|游标id，当使用分页游标方式时返回|否|[number]|1|
|data>>list|详细列表|是|[array]| |
|data>>list>>local_name|本地SKU品名|是|[string]|2-白色-M|
|data>>list>>modify_time|操作时间|是|[string]|2021-06-24 22:09:43|
|data>>list>>msku|MSKU|是|[string]|custom001|
|data>>list>>sku|本地SKU|是|[string]|Book-A4-60|
|data>>list>>store_id|店铺ID|是|[string]|11084135313207808|
|data>>list>>store_name|店铺名称|是|[string]|eBay店铺1号|
|data>>list>>platform_code|平台码|是|[string]|10003|
|data>>list>>platform_name|平台名称|是|[string]|||

## 返回请求示例
```
{
    "code": 0,
    "data": {
        "total": "1",
        "list": [
            {
                "store_id": "11084135313207808",
                "store_name": "eBay店铺1号",
                "platform_code": "10003",
                "platform_name": "eBay",
                "msku": "custom001",
                "sku": "Book-A4-60",
                "local_name": "2-白色-M",
                "modify_time": "2021-06-24 22:09:43"
            }
        ]
    },
    "response_time": "2024-07-23 11:37:43",
    "message": "操作成功",
    "request_id": "1e76129e-c622-420f-852e-08262755cfcc.1721705863164"
}
```
# 查询本地产品列表
支持查询产品列表，对应系统【产品】>【产品管理】数据

## 接口信息

| API Path | 请求协议 | 请求方式 | [令牌桶容量](/docs/Guidance/newInstructions?id=_5-限流算法说明) |
| :------------ | :------------ | :------------ | :------------ |
| `/erp/sc/routing/data/local_inventory/productList` | HTTPS | POST | 1 |
 
## 请求参数

| 参数名 | 说明 | 必填 | 类型 |  示例 |
| :------------ | :------------ | :------------ | :------------ | :------------ |
|offset|分页偏移量，默认0|否|[int]|0|
|length|分页长度，默认1000，上限1000|否|[int]|1000|
|update_time_start|更新时间-开始时间【时间戳，单位：秒，左闭右开】|否|[int]|1719799582|
|update_time_end|更新时间-结束时间【时间戳，单位：秒，左闭右开】|否|[int]|1721873182|
|create_time_start|创建时间-开始时间【时间戳，单位：秒，左闭右开】|否|[int]|1606790813|
|create_time_end|创建时间-结束时间【时间戳，单位：秒，左闭右开】|否|[int]|1609343999|
|sku_list|本地产品sku|否|[array]|["ceshi001","lingcui001","01"]|
|sku_identifier_list|sku识别码列表|否|[array]|["ceshi001","lingcui001","01"]|

## 请求示例
```
{
    "offset": 0,
    "length": 1000,
    "update_time_start": "1719799582",
    "update_time_end": "1721873182",
    "create_time_start": "1606790813",
    "create_time_end": "1609343999",
    "sku_list": ["ceshi001","lingcui001","01"]
}
```

## 返回结果
Json Object

| 参数名 | 说明 | 必填 | 类型 | 示例 |  
| :------------ | :------------ | :------------ | :------------ | :------------ |  
|code|状态码，0 成功|是|[int]|0|
|message|消息提示|是|[string]|success|
|error_details|错误信息|是|[array]|  |
|request_id|请求链路id|是|[string]|A2272BA2-88BC-2908-39AC-680EBE954AD8|
|response_time|响应时间|是|[string]|2020-05-18 11:23:47|
|total|总数|是|[int]|1|
|data|响应数据|是|[array]|  |
|data>>id|本地产品id|是|[int]|1|
|data>>cid|类别id|是|[int]|2|
|data>>category_name|类别|是|[string]|香薰机12|
|data>>bid|品牌id|是|[int]|1|
|data>>brand_name|品牌|是|[string]|手机电子|
|data>>sku|本地产品SKU|是|[string]|视觉111|
|data>>open_status|产品开启状态：  0-停用 ，1-启用|否|[int]|1|
|data>>sku_identifier|SKU识别码|是|[string]|视觉111|
|data>>product_name|品名|是|[string]|经济|
|data>>pic_url|图片链接|是|[string]|https://xxx/abe7be9439b8bb1865d6723f0a2.jpg|
|data>>ps_id|SPU唯一id|是|[int]|1|
|data>>spu|SPU|是|[string]|SPUAAA|
|data>>cg_delivery|采购：交期|是|[int]|13|
|data>>cg_transport_costs|采购：运输成本|是|[number]|25.00|
|data>>purchase_remark|采购备注|是|[string]|  |
|data>>cg_price|采购：采购成本（人民币）|是|[number]|1.00|
|data>>open_status|产品是否启用：0 停用，1 启用|是|[int]|1|
|data>>status|状态：0 停售，1 在售，2 开发中，3 清仓|是|[int]|1|
|data>>status_text|状态文本|是|[string]|在售|
|data>>is_combo|是否为组合产品：0 否，1 是|是|[int]|0|
|data>>create_time|创建时间|是|[int]|1541575627|
|data>>update_time|更新时间|是|[int]|1688531598|
|data>>global_tags|产品标签信息|是|[array]| |
|data>>global_tags>>global_tag_id|标签id|是|[string]| |
|data>>global_tags>>tag_name|标签名称|是|[string]| |
|data>>global_tags>>color|标签颜色|是|[string]| |
|data>>product_developer_uid|开发人员id|是|[string]|2|
|data>>product_developer|开发人员名称|是|[string]|测试账号2|
|data>>cg_opt_uid|采购：采购员id|是|[string]|  |
|data>>cg_opt_username|采购：采购员名称|是|[string]|  |
|data>>supplier_quote|供应商报价信息|是|[array]|  |
|data>>supplier_quote>>psq_id|供应商报价id|是|[string]|  |
|data>>supplier_quote>>product_id|产品id|是|[int]|  |
|data>>supplier_quote>>supplier_id|供应商id|是|[int]| |
|data>>supplier_quote>>is_primary|是否为首选供应商：0 否，1 是|是|[int]|  |
|data>>supplier_quote>>supplier_product_url|采购链接|是|[array]|  |
|data>>supplier_quote>>quote_remark|供应商报价备注|是|[string]|  |
|data>>supplier_quote>>cg_price|采购成本|是|[string]|  |
|data>>supplier_quote>>cg_currency_icon|采购成本币种符号|是|[string]|  |
|data>>supplier_quote>>supplier_code|供应商代码|是|[string]| |
|data>>supplier_quote>>level_text|级别|是|[string]|  |
|data>>supplier_quote>>employees_text|规模|是|[string]|  |
|data>>supplier_quote>>remark|供应商备注|是|[string]|  |
|data>>supplier_quote>>supplier_name|供应商名称|是|[string]|  |
|data>>supplier_quote>>quotes|报价数据|是|[array]|  |
|data>>supplier_quote>>quotes>>currency|报价币种|是|[string]|  |
|data>>supplier_quote>>quotes>>currency_icon|报价币种符号|是|[string]|  |
|data>>supplier_quote>>quotes>>is_tax|是否含税：0 否 1 是|是|[int]|  |
|data>>supplier_quote>>quotes>>tax_rate|税率（百分比）|是|[number]|  |
|data>>supplier_quote>>quotes>>step_prices|报价梯度|是|[array]|  |
|data>>supplier_quote>>quotes>>step_prices>>moq|最小采购量|是|[int]|  |
|data>>supplier_quote>>quotes>>step_prices>>price|不含税单价|是|[number]|  |
|data>>supplier_quote>>quotes>>step_prices>>price_with_tax|含税单价|是|[number]| |
|data>>custom_fields|自定义字段|是|[array]|  |
|data>>custom_fields>>id|字段ID|是|[string]|  |
|data>>custom_fields>>name|字段名|是|[string]|  |
|data>>custom_fields>>val_text|字段值|是|[string]| |
|data>>attribute|产品属性|是|[array]|  |
|data>>attribute>>attr_id|属性ID|是|[string]|  |
|data>>attribute>>attr_name|属性名称|是|[string]|  |
|data>>attribute>>attr_value|属性值|是|[string]| &nbsp; |



## 返回成功示例
```
{
    "code": 0,
    "message": "success",
    "error_details": [],
    "request_id": "A2272BA2-88BC-2908-39AC-680EBE954AD8",
    "response_time": "2021-11-12 16:05:47",
    "data": [
        {
            "id": 17835,
            "cid": 0,
            "bid": 0,
            "sku": "654654654654",
            "sku_identifier": "654654654654",
            "product_name": "13131321655",
            "pic_url": "https://xxx/xxx.jpeg",
            "ps_id": 12,
            "spu": "spu-123",
            "cg_delivery": 555,
            "cg_transport_costs": "0.00",
            "purchase_remark": "20",
            "cg_price": "10.0000",
            "open_status": 1,
            "status": 1,
            "status_text": "在售",
            "is_combo": 0,
            "create_time": 1675945140,
            "update_time": 1675945635,
            "product_developer_uid": 0,
            "product_developer": "",
            "cg_opt_uid": 10317904,
            "cg_opt_username": "xx",
            "brand_name": "",
            "category_name": "",
            "global_tags":[],
            "supplier_quote": [
                {
                    "psq_id": 210279523458442241,
                    "product_id": 17835,
                    "supplier_id": 317,
                    "is_primary": 1,
                    "supplier_product_url": [
                        "https://axxx/xxx"
                    ],
                    "quote_remark": "备注22222222",
                    "cg_price": "10.0000",
                    "cg_currency_icon": "￥",
                    "supplier_name": "橡胶制品",
                    "supplier_code": "SU00306",
                    "level_text": "★★★★★",
                    "employees_text": "1000人以上",
                    "remark": "备注1",
                    "quotes": [
                        {
                            "currency": "CNY",
                            "currency_icon": "￥",
                            "is_tax": 0,
                            "tax_rate": 0,
                            "step_prices": [
                                {
                                    "moq": 0,
                                    "price": "0.0000",
                                    "price_with_tax": "0.0000"
                                }
                            ]
                        }
                    ]
                }
            ],
            "custom_fields": [
                {
                    "id": "207257295331418113",
                    "name": "自定义",
                    "val_text": ""
                }
            ]
        }
    ],
    "total": 1
}
```

## 返回失败示例

```
{
    "code": 500,
    "message": "内部错误",
    "error_details": "offset 必须是非负数 [请求码:C365FF]",
    "request_id": "0A754F01-588E-C019-2693-5B72CF31D914",
    "response_time": "2021-11-11 18:26:35",
    "data": [],
    "total": 0
}
```


# 查询Walmart在线商品
## 接口信息



| API Path | 请求协议 | 请求方式 | [令牌桶容量](/docs/Guidance/newInstructions?id=_5-限流算法说明) |
| :------------ | :------------ | :------------ | :------------ |
| `/basicOpen/multiplatform/walmart/list` | HTTPS | POST | 1 |

## 请求参数

| 参数名 | 说明 | 必填 | 类型 | 示例 |
| :------------ | :------------ | :------------ | :------------ | :------------ |
|offset|分页偏移量，默认0|否|[int]|0|
|length|分页长度，默认20，上限200|否|[int]|20|
|store_ids|店铺id|否|[array]|["11084132377317376"]|
|status|状态：<br>0 PUBLISHED<br>1 READY TO PUBLISH<br>2 IN PROGRESS<br>3 UNPUBLISHED<br>4 STAGE<br>5 SYSTEM PROBLEM|否|[array]|[0]|
|fulfillment_types|发货方式：<br>0 WFS Eligible<br>1 Walmart Fulfilled<br>2 Seller Fulfilled|否|[array]|[0]|
|listing_time_field|搜索时间类型：<br>1 创建时间<br>2 更新时间|否|[int]|1|
|listing_start_time|开始日期，Y-m-d，闭区间【开始结束时间不超过31天】|否|[string]|2024-08-12|
|listing_end_time|结束日期，Y-m-d，闭区间【开始结束时间不超过31天】|否|[string]|2024-09-11|
|search_field|搜索字段类型：<br>1 MSKU<br>2 商品ID<br>3 SKU<br>4 标题|否|[int]|1|
|search_single_value|搜索值(字符串,单个模糊搜索)|否|[string]|114|

## 请求示例
```
{
    "store_ids": [
        "110000000018008002",
        "110000000018008001"
    ],
    "status": [
        0,
        1
    ],
    "fulfillment_types": [
        0
    ],
    "offset": 0,
    "length": 50,
    "search_field": 1,
    "search_single_value": "test",
    "listing_time_field": 1,
    "listing_start_time": "2024-09-01",
    "listing_end_time": "2024-09-13"
}
```

## 返回结果
Json Object

| 参数名  | 说明 | 必填 | 类型 | 示例 |
| :------------ | :------------ | :------------ | :------------ | :------------ |
|code|状态码，0：成功|是|[int]|0|
|message|消息提示|是|[string]|success|
|error_details|数据校验失败时的错误详情|是|[array]| |
|request_id|请求链路id|是|[string]|01b631804c454b68bbb163a8c3137510.1726021186519|
|response_time|响应时间|是|[string]|2024-09-11 10:19:48|
|data|响应数据|是|[object]| |
|data>>list| |是|[array]| |
|data>>list>>item_url|产品跳转链接|是|[string]|http: //www.walmart.com/ip/FBSPORT-Round-Inflatable-Air-Gymnastics-Mat-Training-Mats-4-8-inches-Thickness-Tracks-Home-Use-Training-Cheerleading-Yoga-Water-Pump/815415576|
|data>>list>>item_id|商品ID|是|[string]|wal-0726-102|
|data>>list>>picture_url|图片链接|是|[string]|"https://i5.walmartimages.com/asr/3498e623-4de1-4d4e-8780-d1571dd2af14.5596ac930b26139b73c49a8145501e83.jpeg"|
|data>>list>>msku|MSKU|是|[string]|wal-0726-102|
|data>>list>>title|标题|是|[string]|FBSPORT Round Inflatable Air Gymnastics Mat Training Mats 4/8 inches Thickness Gymnastics Tracks for Home Use,Training,Cheerleading,Yoga,Water with Pump|
|data>>list>>local_name|品名|是|[string]|kun'bang12|
|data>>list>>local_sku|SKU|是|[string]|kunbang12|
|data>>list>>status_name|状态|是|[string]|PUBLISHED|
|data>>list>>store_id|店铺id|是|[string]|110000000018008002|
|data>>list>>store_name|店铺名|是|[string]|test18自创walmart测试店铺2号1|
|data>>list>>currency_icon|货币种类|是|[string]|$|
|data>>list>>price|价格|是|[string]|139.90|
|data>>list>>available_quantity|非WFS可售|是|[int]|12|
|data>>list>>quantityAdjustAfter|库存调整后的值|是|[string]|10|
|data>>list>>quantityAdjustBefore|库存调整前的值|是|[string]|12|
|data>>list>>quantityUserId|库存调整操作人id|是|[string]|10325676|
|data>>list>>quantityUserIdName|库存调整操作人名称|是|[string]|张焕杰|
|data>>list>>wfs_available_quantity|WFS可售数量|是|[int]|32|
|data>>list>>buy_box_price|Buy Box价格|是|[string]|139.90|
|data>>list>>buy_box_shipping_price|Buy Box运费|是|[string]|0.00|
|data>>list>>gtin|gtin|是|[string]|00723849594300|
|data>>list>>upc|upc|是|[string]|723849594300|
|data>>list>>product_tax_code|商品税号|是|[string]|2038710|
|data>>list>>offer_start_date|销售开始时间|是|[string]|2021-03-24 00:00:00|
|data>>list>>offer_end_date|销售结束时间|是|[string]|2049-12-30 00:00:00|
|data>>list>>review_count|评论数|是|[string]|0|
|data>>list>>average_rating|评分|是|[string]| |
|data>>list>>brand|品牌|是|[string]|FBsport|
|data>>list>>fulfillment_type|发货方式:<br>0 WFS Eligible<br>1 Walmart Fulfilled<br>2 Seller Fulfilled|是|[int]|2|
|data>>list>>fulfillment_type_name|发货方式:<br>0 WFS Eligible<br>1 Walmart Fulfilled<br>2 Seller Fulfilled|是|[string]|Seller Fulfilled|
|data>>list>>competitor_price|竞品价格|是|[string]|139.99|
|data>>list>>competitor_ship_price|竞品运费|是|[string]|0.00|
|data>>list>>listing_start_time|创建时间|是|[string]|2021-03-25 00:00:00|
|data>>list>>listing_end_time|结束时间|是|[string]|2022-02-23 00:00:00|
|data>>list>>variant_unique_id|变体唯一id|是|[string]| 901207962317777|
|total|总数|是|[int]|41275|

## 返回成功示例
```
{
    "code": 0,
    "message": "success",
    "error_details": [],
    "request_id": "a0d54debf93140f3b58d1ed81e8e3583.105.17262205381773389",
    "response_time": "2024-09-13 17:42:18",
    "data": [
        {
            "item_url": "http: //www.walmart.com/ip/FBSPORT-Rounness-Tracks-Home-Use-Training-Cheerleading-Yoga-Water-Pum15576",
            "item_id": "wal-0726-100",
            "msku": "wal-0726-100",
            "title": "FBSPORT Round Inflatable Air Gymnastics Mat Tr with Pump",
            "local_name": "wjc14_pm",
            "local_sku": "wjc14_sku",
            "status_name": "PUBLISHED",
            "store_id": "11000000001802",
            "store_name": "test18自创walm店铺2号1",
            "currency_icon": "$",
            "price": "139.90",
            "available_quantity": 12,
            "quantityAdjustAfter": null,
            "quantityAdjustBefore": null,
            "quantityUserId": null,
            "quantityUserIdName": "",
            "wfs_available_quantity": 32,
            "buy_box_price": "139.90",
            "buy_box_shipping_price": "0.00",
            "gtin": "00723849594300",
            "upc": "723849594300",
            "product_tax_code": "2038710",
            "offer_start_date": "2021-03-24 00:00:00",
            "offer_end_date": "2049-12-30 00:00:00",
            "review_count": "0",
            "average_rating": "",
            "brand": "FBsport",
            "fulfillment_type": 2,
            "fulfillment_type_name": "Seller Fulfilled",
            "competitor_price": "139.99",
            "competitor_ship_price": "0.00",
            "listing_start_time": "2021-03-25 00:00:00",
            "listing_end_time": "2022-02-23 00:00:00",
            "variant_unique_id": "901209431054963712"
        }
    ],
    "total": 41275
}
```
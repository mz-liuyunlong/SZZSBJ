# 查询本地产品详情
支持查询本地产品详细信息，对应系统【产品】>【产品管理】数据

>product_logistics_relation参数说明数组子元素中各前缀的含义：<br>
US（美国）、CA（加拿大）、MX（墨西哥）、JP（日本）、UK（英国）、DE（德国）、FR（法国）、ES（西班牙）、IT（意大利）、NL（荷兰）、
AU（澳洲）、SG（新加坡）、IN（印度）、AE（阿联酋）、SA（沙特阿拉伯）、BR（巴西）、SE（瑞典）、PL（波兰）、BE（比利时）、TR（土耳其）、
UA（乌克兰）、HU（匈牙利）、PK（巴基斯坦）、LB（黎巴嫩）、AT（奥地利）、CH（瑞士）、CZ（捷克）、DK（丹麦）、IE（爱尔兰）、LU（卢森堡）、
NO（挪威）、PT（葡萄牙）、SK（斯洛伐克）、RU（俄罗斯）、KZ（哈萨克斯坦）、BY（白俄罗斯）、CL（智利）、KR（韩国）

## 接口信息

| API Path | 请求协议 | 请求方式 | [令牌桶容量](/docs/Guidance/newInstructions?id=_5-限流算法说明) |
| :------------ | :------------ | :------------ | :------------ |
| `/erp/sc/routing/data/local_inventory/productInfo` | HTTPS | POST | 1 |

## 请求参数

| 参数名 | 说明 | 必填 | 类型 | 示例 |  
| :------------ | :------------ | :------------ | :------------ | :------------ |  
| id |产品id【产品id、 产品SKU 、SKU识别码 三选一必填】|否| [int] |10001|
| sku|产品SKU【产品id、 产品SKU 、SKU识别码 三选一必填】|否|[string]|ceshi001|
| sku_identifier|SKU识别码【产品id、 产品SKU 、SKU识别码 三选一必填】|否|[string]|ceshi001|

## 请求示例
```
{
    "id": 10001,
    "sku": "ceshi001"
}
```

## 返回结果
Json Object

| 参数名  | 说明| 必填 | 类型       |  示例 |
| :------------ |:------------------------------------------------------------------------| :------------ |:---------| :------------ |
|code| 状态码，0 成功                                                                |是| [int]    |0|
|message| 消息提示|是| [string] |success|
|error_details| 错误提示|是| [array]  | |
|request_id| 请求链路id|是| [string] |F44E6A41-5219-4FEF-DD46-5BCC4B8305E1|
|response_time| 响应时间|是| [string] |2021-03-19 11:53:49|
|data| 产品数据|是| [object] |  |
|data>>id| 本地产品id|是| [int]    |1|
|data>>product_name| 产品名称|是| [string] |00.100|
|data>>sku| 产品sku|是| [string] |视觉111|
|data>>sku_identifier| SKU识别码|是| [string] |视觉111|
|data>>pic_url| 上传的图片地址                                                                 |是| [string] |xxx/xxx/78f2dc9409b6c6abe8f15ed5eb.jpg|
|data>>picture_list| 产品图片数组|是| [array]  |  |
|data>>picture_list>>pic_url| 图片链接|是| [string] |  |
|data>>picture_list>>is_primary| 是否产品主图：0-否 1-是                                                          |是| [int]    |  |
|data>>model| 产品型号|是| [string] |  |
|data>>unit| 商品单位：套、个、台|是| [string] |  |
|data>>status| 状态：0 停售，1 在售，2 开发中，3 清仓                                                 |是| [int]    |1|
|data>>cid| 分类id|是| [int]    |1099|
|data>>bid| 品牌id|是| [int]    |1324|
|data>>product_developer| 开发者                                                                     |是| [string] |  |
|data>>product_developer_uid| 开发人                                                                     |是| [int]    | |
|data>>permission_user_info| 负责人数组|是| [array]  | |
|data>>permission_user_info>>permission_uid| 负责人id|是| [int]    | |
|data>>permission_user_info>>permission_user_name| 负责人名称|是| [string] | |
|data>>global_tags| 产品标签信息|是| [array]  | |
|data>>global_tags>>global_tag_id| 标签id|是| [string] | |
|data>>global_tags>>tag_name| 标签名称|是| [string] | |
|data>>global_tags>>color| 标签颜色|是| [string] | |
|data>>description| 产品描述|是| [string] |<p>goods</p>|
|data>>is_combo| 是否为组合产品：0 否，1 是|是| [int]    | |
|data>>brand_name| 品牌名称|是| [string] |api-72|
|data>>category_name| 分类名称|是| [string] |类476422|
|data>>attachment_id| 附件id|是| [array]  |[123]|
|data>>special_attr| 产品特殊属性：<br>1 含电<br>2 纯电<br>3 液体<br>4 粉末<br>5 膏体<br>6 带磁                 |是| [array]  |[1,2,3]|
|data>>currency| 中国官方汇率code|是| [string] |USD|
|data>>cg_opt_username| 采购：采购员|是| [string] |0超级管理员22222|
|data>>cg_delivery| 采购：交期|是| [int]    |13|
|data>>cg_price| 采购：采购成本（人民币）|是| [number] |34.0000|
|data>>purchase_remark| 采购备注|是| [string] | |
|data>>cg_product_material| 采购：材质|是| [string] |11|
|data>>cg_product_length| 采购：产品规格（CM）|是| [number] |12.0|
|data>>cg_product_width| 采购：产品规格（CM）|是| [number] |13.0|
|data>>cg_product_height| 采购：产品规格（CM）|是| [number] |14.0|
|data>>cg_package_length| 采购：包装规格（CM）|是| [number] |16.0|
|data>>cg_package_width| 采购：包装规格（CM）|是| [number] |17.0|
|data>>cg_package_height| 采购：包装规格（CM）|是| [number] |18.0|
|data>>cg_box_length| 采购：外箱规格（CM）|是| [number] |20.0|
|data>>cg_box_width| 采购：外箱规格（CM）|是| [number] |21.0|
|data>>cg_box_height| 采购：外箱规格（CM）|是| [number] |22.0|
|data>>cg_product_net_weight| 采购：产品净重（G）|是| [number] |15.00|
|data>>cg_product_gross_weight| 采购：产品毛重（G）|是| [number] |33.00|
|data>>cg_box_weight| 采购：外箱实重（KG）|是| [number] |23.00|
|data>>custom_fields|自定义字段|是|[array]|  |
|data>>custom_fields>>id|字段ID|是|[string]|  |
|data>>custom_fields>>name|字段名|是|[string]|  |
|data>>custom_fields>>val_text|字段值|是|[string]| |
|data>>cg_box_pcs| 采购：单箱数量（包装数量）                                                           |是| [int]    |25|
|data>>bg_customs_export_name| 报关：申报品名（中文）【中文报关名】                                                      |是| [string] |测试测|
|data>>bg_customs_import_name| 报关：申报品名（英文）【英文报关名】                                                      |是| [string] |ceshice|
|data>>bg_customs_import_price| 报关：申报金额（进口国）【申报单价】                                                      |是| [number] |30.00|
|data>>bg_export_hs_code| 报关：HS Code（出口国）【中国HS Code】                                              |是| [string] |USD|
|data>>bg_import_hs_code| 报关：HS Code（进口国）【美国HS Code】                                              |是| [string] |29|
|data>>bg_tax_rate| 【已废弃字段】报关：税率【美国税率】                                                      |是| [number] |28.0000|
|data>>qc_standard| 质检标准|是| [object] | |
|data>>qc_standard>>custom_qc_template| 自定义质检标准                                                                 |否| [object] | |
|data>>qc_standard>>custom_qc_template>>qc_image| 质检图片(字段待废弃，请使用质检图片-新)|是| [array]  | |
|data>>qc_standard>>custom_qc_template>>qc_image>>file_id| 领星文件id|否| [int]    | |
|data>>qc_standard>>custom_qc_template>>qc_image>>customer_url| 客户的图片URL|否| [string] | |
|data>>qc_standard>>custom_qc_template>>qc_images| 质检图片-新|是| [array]  | |
|data>>qc_standard>>custom_qc_template>>qc_images>>file_id| 领星文件id|是| [string] | |
|data>>supplier_quote| 供应商报价数据                                                                 |是| [array]  |  |
|data>>supplier_quote>>psq_id| 供应商报价id                                                                 |是| [string] |  |
|data>>supplier_quote>>product_id| 产品id|是| [int]    |  |
|data>>supplier_quote>>supplier_id| 供应商id|是| [int]    |  |
|data>>supplier_quote>>supplier_name| 供应商名称|是| [string] | |
|data>>supplier_quote>>is_primary| 是否为首选供应商：0 否，1 是                                                        |是| [int]    |  |
|data>>supplier_quote>>quote_remark| 报价备注|是| [string] | |
|data>>supplier_quote>>supplier_product_url| 采购链接|是| [array]  |  |
|data>>supplier_quote>>quote_cg_delivery| 交期|是| [int]    |  |
|data>>supplier_quote>>quotes| 报价数据|是| [array]  |  |
|data>>supplier_quote>>quotes>>currency| 报价币种|是| [string] |  |
|data>>supplier_quote>>quotes>>currency_icon| 报价币种符号|是| [string] |  |
|data>>supplier_quote>>quotes>>is_tax| 是否含税：0 否，1 是|是| [int]    |  |
|data>>supplier_quote>>quotes>>tax_rate| 税率（百分比）                                                                 |是| [string] |  |
|data>>supplier_quote>>quotes>>step_prices| 阶梯报价|是| [array]  |  |
|data>>supplier_quote>>quotes>>step_prices>>moq| 最小采购量|是| [int]    |  |
|data>>supplier_quote>>quotes>>step_prices>>price| 不含税单价|是| [number] |  |
|data>>supplier_quote>>quotes>>step_prices>>price_with_tax| 含税单价|是| [number] |  |
|data>>combo_product_list| 组合产品列表|是| [array]  | |
|data>>combo_product_list>>product_id| 本地产品id|是| [int]    | |
|data>>combo_product_list>>quantity| 数量|是| [int]    | |
|data>>combo_product_list>>sku| SKU                                                                     |是| [string] | |
|data>>product_logistics_relation| 物流关联【XX为国家简码，比如美国 US】                                                   |是| [array]  ||
|data>>product_logistics_relation>>XX_cg_transport_costs| 默认头程成本(含税)|是| [number] ||
|data>>product_logistics_relation>>XX_currency| 官方汇率code                                                                |是| [string] ||
|data>>product_logistics_relation>>XX_clearance_price| 清关价格|是| [number] | |
|data>>product_logistics_relation>>XX_clearance_price_currency| 清关价格币种|是| [string] | |
|data>>product_logistics_relation>>XX_bg_import_hs_code| 报关：HSCode（进口国）                                                          |是| [string] ||
|data>>product_logistics_relation>>XX_bg_tax_rate| 报关：税率|是| [number] ||
|data>>declaration| 报关数据|是| [object] | |
|data>>declaration>>customs_declaration_unit| 报关单位|是| [string] | |
|data>>declaration>>customs_declaration_spec| 规格型号|是| [string] | |
|data>>declaration>>customs_declaration_origin_produce| 报关：原厂国（地区）|是| [string] | |
|data>>declaration>>customs_declaration_inlands_source| 报关：境内货源地                                                                |是| [string] | |
|data>>declaration>>other_declare_element| 报关：其他申报要素                                                               |是| [string] | |
|data>>declaration>>customs_declaration_exempt| 报关：征免|是| [string] | |
|data>>declaration>>customs_import_price|报关单价|否| [string] | |
|data>>declaration>>customs_import_price_currency|报关单价单位|否| [string] | |
|data>>declaration>>production_and_sales_enterprise_name|报关：生产销售企业名称|是| [string] | |
|data>>declaration>>production_and_sales_enterprise_code|报关：生产销售企业代码|是| [string] | |
|data>>clearance| 清关数据|是| [object] | |
|data>>clearance>>customs_clearance_material| 清关：材质|是| [string] | |
|data>>clearance>>customs_clearance_usage| 清关：用途|是| [string] | |
|data>>clearance>>customs_clearance_internal_code| 清关：内部编码                                                                 |是| [string] | |
|data>>clearance>>customs_clearance_preferential| 清关：出口享惠情况：<br>1 不享惠<br>2 享惠<br>3 不确定享惠情况                                |是| [int]    | |
|data>>clearance>>customs_clearance_brand_type| 清关：品牌类型：<br>1 无品牌<br>2 境内自主品牌<br>3 境内收购品牌<br>4 境外品牌（贴牌生产）<br>5 境外品牌（其他） |是| [int]    | |
|data>>clearance>>customs_clearance_product_pattern| 清关：产品型号                                                                 |是| [string] | |
|data>>clearance>>customs_clearance_pic_url| 清关：清关图片                                                                 |是| [string] ||
|data>>clearance>>allocation_remark| 清关：配货备注                                                                 |是| [string] | |
|data>>clearance>>weaving_mode| 织造方式：1 针织，2 梭织                                                          |是| [int]    | |
|data>>clearance>>customs_clearance_price| 默认清关单价|是| [string] | |
|data>>clearance>>customs_clearance_price_currency| 默认清关单价币种                                                                |是| [string] | |
|data>>clearance>>customs_clearance_hs_code| 默认清关HSCODE|是| [string] | |
|data>>clearance>>customs_clearance_tax_rate| 默认清关税率|是| [string] | |
|data>>clearance>>customs_clearance_remark| 默认清关备注|是| [string] |&nbsp;|
|data>>aux_relation_list|辅料列表|是|[array]| |
|data>>aux_relation_list>>aux_sku|辅料sku|是|[string]| |
|data>>aux_relation_list>>aux_name|辅料名称|是|[string]| |
|data>>aux_relation_list>>sku_qty|辅料比例（主料）|是|[string]| |
|data>>aux_relation_list>>aux_qty|辅料比例（辅料）|是|[string]| |
|data>>category_full_name|完整分类层级名称|是|[string]|guoze一级分类\\国泽二级分类2\\www|



## 返回成功示例

```
{
    "code": 0,
    "message": "success",
    "error_details": [],
    "request_id": "F4AC348D-5A4D-0F2B-833B-A02678969381",
    "response_time": "2022-07-05 17:05:37",
    "data": {
        "id": 17835,
        "product_name": "13131321655",
        "sku": "654654654654",
        "sku_identifier": "654654654654",
        "pic_url": "https://imaxxx/xx61fb94db6fa2f5.jpeg",
        "model": "",
        "unit": "",
        "status": 1,
        "cid": 0,
        "bid": 0,
        "product_developer": "",
        "product_developer_uid": 0,
        "description": "",
        "is_combo": 0,
        "currency": "USD",
        "purchase_remark": "20",
        "special_attr": [
            "4",
            "3"
        ],
        "attachment_id": [
            "4132"
        ],
        "cg_opt_username": "xx",
        "cg_delivery": 555,
        "cg_price": "10.0000",
        "cg_product_material": "",
        "bg_customs_export_name": "10",
        "bg_customs_import_name": "10",
        "bg_customs_import_price": "10.000000",
        "bg_export_hs_code": "10",
        "bg_import_hs_code": "",
        "bg_tax_rate": "0.0000",
        "picture_list": [
            {
                "pic_url": "https://imaxxx/xx61fb94db6fa2f5.jpeg",
                "is_primary": 1
            }
        ],
        "permission_user_info": [
            {
                "permission_uid": 10317904,
                "permission_user_name": "xx"
            }
        ],
        "brand_name": "",
        "category_name": "",
        "supplier_quote": [
            {
                "psq_id": "210331084332590081",
                "product_id": "17835",
                "supplier_id": "317",
                "is_primary": 1,
                "supplier_product_url": [
                    "https://xxx/xxx"
                ],
                "quote_cg_delivery": 20240425,
                "quote_remark": "备注22222222",
                "cg_price": "10.0000",
                "cg_currency_icon": "￥",
                "supplier_name": "xxx",
                "supplier_code": "SU00306",
                "quotes": [
                    {
                        "currency": "CNY",
                        "currency_icon": "￥",
                        "is_tax": 0,
                        "tax_rate": "0.00",
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
        "combo_product_list": [],
        "declaration": {
            "customs_declaration_unit": "",
            "customs_declaration_spec": "",
            "customs_declaration_origin_produce": "",
            "customs_declaration_inlands_source": "",
            "customs_declaration_exempt": "",
            "other_declare_element": ""
        },
        "clearance": {
            "customs_clearance_material": "",
            "customs_clearance_usage": "",
            "customs_clearance_internal_code": "",
            "customs_clearance_preferential": 0,
            "customs_clearance_brand_type": 0,
            "customs_clearance_product_pattern": "",
            "customs_clearance_pic_url": "",
            "allocation_remark": "",
            "weaving_mode": 0,
            "customs_clearance_price": "0.0000",
            "customs_clearance_price_currency": "CNY",
            "customs_clearance_hs_code": "",
            "customs_clearance_tax_rate": "0.0000",
            "customs_clearance_remark": ""
        },
        "qc_standard": {
            "custom_qc_template": {
                "qc_image": []
            }
        },
        "product_logistics_relation": [
            {
                "US_cg_transport_costs": "0.0000",
                "US_currency": "CNY",
                "US_bg_import_hs_code": "",
                "US_clearance_price_currency": "CNY",
                "US_clearance_price": "0.00",
                "US_bg_tax_rate": "0.0000"
            }
        ],
        "cg_product_length": "10.00",
        "cg_product_width": "20.00",
        "cg_product_height": "10.00",
        "cg_product_net_weight": "0.00",
        "cg_package_length": "50.00",
        "cg_package_width": "60.00",
        "cg_package_height": "70.00",
        "cg_box_length": "20.00",
        "cg_box_width": "30.00",
        "cg_box_height": "40.00",
        "cg_box_pcs": 10,
        "cg_product_gross_weight": "90000.00",
        "cg_box_weight": "80.00",
        "custom_fields": [
            {
                "id": "207257295331418115",
                "name": "文本",
                "val_text": ""
            }
        ]    
	    "global_tags": []
    },
    "total": 0
}
```

## 返回失败示例

```
{
    "code": 500,
    "message": "内部错误",
    "error_details": "id不能为空 [请求码:C60610]",
    "request_id": "360AB815-F61E-36E6-4CFF-68AA8A6868AF",
    "response_time": "2021-11-11 16:27:36",
    "data": [],
    "total": 0
}
```


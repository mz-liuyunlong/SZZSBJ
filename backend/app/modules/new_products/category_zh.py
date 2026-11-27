"""Stable offline Chinese names for known Walmart category labels.

No network calls and no synthetic category attribution. Values not found in the
catalogue stay explicitly unresolved; missing source remains 未分类.
"""

from __future__ import annotations

import re

# Human-reviewed translations of broad Walmart/retail taxonomy categories.
# Preserve meaningful distinctions between categories; do not collapse them to
# overly broad names just to produce Chinese text.
_CATEGORY_ZH = {
    "appliances": "家用电器",
    "air conditioners": "空调",
    "air fryers": "空气炸锅",
    "automotive": "汽车用品",
    "auto & tires": "汽车与轮胎",
    "arts & crafts": "艺术与手工艺",
    "arts crafts & sewing": "艺术、手工艺与缝纫",
    "arts crafts and sewing": "艺术、手工艺与缝纫",
    "baby": "母婴用品",
    "baby products": "母婴用品",
    "baby & toddler": "婴幼儿用品",
    "bakeware": "烘焙器具",
    "baking": "烘焙用品",
    "bath": "浴室用品",
    "bathroom": "浴室用品",
    "bathroom accessories": "浴室配件",
    "beauty": "美妆",
    "beauty & personal care": "美妆与个护",
    "beauty and personal care": "美妆与个护",
    "bedding": "床上用品",
    "bed & bath": "寝具与浴室用品",
    "bed and bath": "寝具与浴室用品",
    "bedroom furniture": "卧室家具",
    "books": "图书",
    "business & industrial": "商业与工业用品",
    "cameras & photo": "相机与摄影",
    "car accessories": "汽车配件",
    "car care": "汽车养护",
    "cleaning": "清洁用品",
    "cleaning supplies": "清洁用品",
    "clothing": "服装",
    "clothing shoes & accessories": "服装、鞋靴与配饰",
    "clothing shoes and accessories": "服装、鞋靴与配饰",
    "coffee & tea": "咖啡与茶饮",
    "coffee makers": "咖啡机",
    "computer accessories": "电脑配件",
    "computers": "电脑",
    "computers & tablets": "电脑与平板",
    "cookware": "炊具",
    "cookware sets": "炊具套装",
    "cooking utensils": "烹饪用具",
    "countertop appliances": "台面小家电",
    "crafts": "手工艺用品",
    "dairy": "乳制品",
    "decor": "装饰用品",
    "dining": "餐饮用品",
    "dining & entertaining": "餐饮与宴客用品",
    "dining and entertaining": "餐饮与宴客用品",
    "dinnerware": "餐具",
    "dishes": "餐盘与碗碟",
    "disposable tableware": "一次性餐具",
    "drinkware": "饮具",
    "electronics": "电子产品",
    "electronics accessories": "电子产品配件",
    "entryway furniture": "玄关家具",
    "event & party supplies": "活动与派对用品",
    "exercise & fitness": "运动健身用品",
    "fabric": "布料",
    "fashion": "时尚用品",
    "fishing": "钓鱼用品",
    "fitness": "健身用品",
    "floor care": "地面清洁用品",
    "food": "食品",
    "food & beverage": "食品与饮料",
    "food & grocery": "食品与杂货",
    "food storage": "食品收纳",
    "food storage containers": "食品保鲜容器",
    "furniture": "家具",
    "games": "游戏用品",
    "garden": "园艺",
    "garden & outdoors": "园艺与户外",
    "garden center": "园艺中心",
    "gifts": "礼品",
    "grocery": "食品杂货",
    "grocery & gourmet food": "食品杂货与精品食品",
    "hair care": "头发护理",
    "hardware": "五金用品",
    "health": "健康用品",
    "health & beauty": "健康与美容",
    "health & household": "健康与家庭用品",
    "health and household": "健康与家庭用品",
    "home": "家居",
    "home & garden": "家居与园艺",
    "home and garden": "家居与园艺",
    "home & kitchen": "家居与厨房",
    "home and kitchen": "家居与厨房",
    "home decor": "家居装饰",
    "home decoration": "家居装饰",
    "home improvement": "家居装修",
    "home organization": "家居收纳",
    "home storage": "家居收纳",
    "household": "家庭日用品",
    "household cleaning": "家庭清洁用品",
    "household essentials": "家庭日用品",
    "household supplies": "家庭日用品",
    "housewares": "家居日用品",
    "indoor furniture": "室内家具",
    "industrial & scientific": "工业与科研用品",
    "jewelry": "珠宝饰品",
    "kitchen": "厨房用品",
    "kitchen & dining": "厨房与餐饮",
    "kitchen and dining": "厨房与餐饮",
    "kitchen appliances": "厨房电器",
    "kitchen accessories": "厨房配件",
    "kitchen gadgets": "厨房小工具",
    "kitchen gadgets & tools": "厨房工具",
    "kitchen tools": "厨房工具",
    "kitchen tools & gadgets": "厨房工具与小器具",
    "kitchen tools and gadgets": "厨房工具与小器具",
    "kitchen utensils": "厨房用具",
    "kitchenware": "厨具",
    "laundry": "洗衣用品",
    "laundry & cleaning": "洗衣与清洁用品",
    "laundry room": "洗衣房用品",
    "lawn & garden": "庭院与园艺",
    "lawn and garden": "庭院与园艺",
    "lighting": "照明用品",
    "living room": "客厅用品",
    "living room furniture": "客厅家具",
    "luggage": "箱包",
    "luggage & travel": "箱包与旅行用品",
    "major appliances": "大型家电",
    "medical supplies": "医疗用品",
    "men": "男士用品",
    "men's clothing": "男装",
    "microwaves": "微波炉",
    "musical instruments": "乐器",
    "office": "办公用品",
    "office & school supplies": "办公与学习用品",
    "office and school supplies": "办公与学习用品",
    "office furniture": "办公家具",
    "office products": "办公用品",
    "office supplies": "办公用品",
    "outdoor": "户外用品",
    "outdoor furniture": "户外家具",
    "outdoor living": "户外生活用品",
    "outdoor recreation": "户外休闲用品",
    "packaging": "包装用品",
    "paper & plastic": "纸品与塑料用品",
    "party": "派对用品",
    "party & occasions": "派对与节庆用品",
    "party supplies": "派对用品",
    "patio": "庭院用品",
    "patio & garden": "庭院与园艺",
    "patio and garden": "庭院与园艺",
    "personal care": "个人护理",
    "pet": "宠物用品",
    "pet supplies": "宠物用品",
    "pets": "宠物用品",
    "plastic storage": "塑料收纳用品",
    "plumbing": "管道与卫浴五金",
    "pots & pans": "锅具",
    "pots and pans": "锅具",
    "power tools": "电动工具",
    "refrigerators": "冰箱",
    "seasonal": "季节性用品",
    "seasonal decor": "节庆装饰",
    "sewing": "缝纫用品",
    "shoes": "鞋靴",
    "small appliances": "小家电",
    "small kitchen appliances": "厨房小家电",
    "smart home": "智能家居",
    "snack containers": "零食收纳容器",
    "sports": "体育用品",
    "sports & outdoors": "运动与户外",
    "sports and outdoors": "运动与户外",
    "storage": "收纳用品",
    "storage & organization": "收纳与整理",
    "storage and organization": "收纳与整理",
    "storage containers": "收纳容器",
    "storage bins": "收纳箱",
    "tableware": "餐桌用品",
    "tabletop": "餐桌用品",
    "tabletop & bar": "餐桌与酒吧用品",
    "tools": "工具",
    "tools & hardware": "工具与五金",
    "tools and hardware": "工具与五金",
    "toys": "玩具",
    "toys & games": "玩具与游戏",
    "toys and games": "玩具与游戏",
    "travel": "旅行用品",
    "vacuum cleaners": "吸尘器",
    "wall decor": "墙面装饰",
    "walmart": "沃尔玛",
    "women": "女士用品",
    "women's clothing": "女装",
}


def _normalize(value: str) -> str:
    text = value.casefold().strip().replace("＆", "&").replace("–", "-")
    text = re.sub(r"[\u00ae\u2122]", "", text)
    text = re.sub(r"[^a-z0-9&' -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip(" -")


# User-verified source paths; exact lookup before broad term matching.
_EXACT_CATEGORY_PATH_ZH = {
    (
        "Arts Crafts & Sewing > Arts & Crafts Furniture and Storage > Craf"
        "t Storage > Craft & Hobby Storage Bags & Cases"
    ): "手工艺 / 手工材料收纳包及收纳盒",
    (
        "Arts Crafts & Sewing > Beading & Jewelry Making > Beading Supplies > Beading Storage"
    ): "手工艺 / 串珠材料收纳",
    (
        "Arts Crafts & Sewing > Crafting > Craft Supplies > Basic Craft Su"
        "pplies > Shop all Basic Craft Supplies"
    ): "手工艺 / 基础手工材料",
    ("Arts Crafts & Sewing > Fabric > Shop Fabric by Size > Fabric by the Yard"): (
        "缝纫布料 / 按码销售布料"
    ),
    ("Auto & Tires > Automotive Replacement Parts > Replacement Auto Parts"): (
        "汽车用品 / 汽车替换零件"
    ),
    "Auto & Tires > Automotive Tools & Equipment > Auto Tool Storage": "汽车用品 / 车载工具收纳",
    (
        "Auto & Tires > Car Safety & Car Security > Car Anti-Theft Devices > Steering Wheel Locks"
    ): "汽车安全 / 方向盘防盗锁",
    (
        "Auto & Tires > Exterior Car Parts & Accessories > Car & Truck Rac"
        "ks, Cargo Carriers & Ratchet Straps > Bungee Cords and Ratchet St"
        "raps > Bungee Cords > Bungee Cords with Hooks"
    ): "汽车用品 / 带钩弹力绑绳",
    (
        "Auto & Tires > Exterior Car Parts & Accessories > Towing Hitches,"
        " Winches & Accessories > Tie Downs, Anchors & Bungees > Tie Downs"
        " And Straps > Shop Tie Downs And Straps by Vehicle > Car Straps"
    ): "汽车用品 / 车辆捆绑带",
    (
        "Auto & Tires > Interior Parts & Accessories > Car Organizers > Back Seat Organizers"
    ): "汽车收纳 / 后座收纳袋",
    (
        "Auto & Tires > Interior Parts & Accessories > Car Organizers > Phone Car Mounts"
    ): "车载配件 / 手机支架",
    (
        "Auto & Tires > Interior Parts & Accessories > Steering Wheel Cove"
        "rs > Steering Wheel Covers by Color > Black Steering Wheel Covers"
    ): "汽车内饰 / 黑色方向盘套",
    (
        "Auto & Tires > Tires & Accessories > Tire and Wheel Accessories >"
        " Tire Inflators > Tire Inflators with Gauge"
    ): "轮胎工具 / 带压力表充气泵",
    "Baby > Health & Safety > Baby Proofing": "母婴安全 / 婴幼儿防护用品",
    "Beauty > Makeup > Makeup Tools and Accessories": "美妆工具 / 化妆工具及配件",
    "Beauty > Womens Hair Accessories": "美妆配饰 / 女士发饰",
    "Clothing > Bags & Accessories > Accessories > Keychains": "服饰配件 / 钥匙扣",
    "Electronics > Audio > Audio Visual Accessories": "电子影音 / 音视频配件",
    (
        "Electronics > Computers, Laptops and Tablets > Computer Accessori"
        "es > Computer Keyboards & Mice > Computer Mouse & Mouse Pads > Mo"
        "use Pads & Wrist Rests"
    ): "电脑配件 / 鼠标垫与腕托",
    "Electronics > Electronics Value Bundles": "电子产品 / 组合套装",
    "Health and Medicine > Massage > Shop all Massagers": "健康按摩 / 按摩器",
    (
        "Health and Medicine > Sports Medicine & Injury Recovery Solution "
        "> Return to Function After Injury > Recover From Surgery > Bathin"
        "g After Surgery"
    ): "康复护理 / 术后洗浴辅助用品",
    (
        "Home > Appliances > Appliances Parts & Accessories > Dishwasher P"
        "arts > Dishwasher Accessories"
    ): "家电配件 / 洗碗机配件",
    "Home > Appliances > Appliances Parts & Accessories > Microwave Parts": "家电配件 / 微波炉零件",
    (
        "Home > Appliances > Appliances Parts & Accessories > Refrigerator"
        " & Freezer Parts > Refrigerator Accessories"
    ): "家电配件 / 冰箱配件",
    (
        "Home > Appliances > Appliances Parts & Accessories > Washer & Dry"
        "er Parts > Dryer Lint Screens"
    ): "家电配件 / 烘干机绒毛过滤网",
    (
        "Home > Appliances > Appliances Parts & Accessories > Washer & Dry"
        "er Parts > Shop All Washer & Dryer Parts"
    ): "家电配件 / 洗衣机及烘干机零件",
    (
        "Home > Appliances > Kitchen Appliances > Coffee Shop > Coffee Decanters & Carafes"
    ): "咖啡器具 / 咖啡壶与玻璃分享壶",
    (
        "Home > Appliances > Kitchen Appliances > Kitchen Appliance Parts "
        "& Accessories > Coffee & Espresso Parts and Accessories"
    ): "咖啡器具 / 咖啡机及意式咖啡机配件",
    (
        "Home > Appliances > Kitchen Appliances > Mixers & Attachments > S"
        "hop All Mixers & Attachments"
    ): "厨房电器 / 搅拌机及配件",
    (
        "Home > Appliances > Vacuums, Steamers & Floor Care > Steam Mop Pads & Brushes"
    ): "清洁电器 / 蒸汽拖把替换垫和刷头",
    (
        "Home > Appliances > Vacuums, Steamers & Floor Care > Vacuum Accessories & Parts"
    ): "清洁电器 / 吸尘器配件与零件",
    "Home > Bath > Bathroom Accessories > Soap Dispensers": "浴室用品 / 皂液器",
    "Home > Bath > Bathroom Accessories > Tissue Box Cover": "浴室用品 / 纸巾盒罩",
    "Home > Bath > Bathroom Rugs & Bath Mats > Bathtub Mats": "浴室防滑 / 浴缸防滑垫",
    "Home > Bath > Bathroom Storage": "浴室用品 / 浴室收纳",
    (
        "Home > Decor > Artificial Plants and Flowers > All Artificial Plants and Flowers"
    ): "家居装饰 / 仿真植物与花卉",
    "Home > Decor > Artificial Plants and Flowers > Artificial Flowers": "家居装饰 / 仿真花",
    "Home > Decor > Candles & Home Fragrance > Candle Holders": "家居香氛 / 烛台",
    (
        "Home > Decor > Curtains & Window Treatments > Curtain Hanging Acc"
        "essories > Curtain Hardware"
    ): "窗帘配件 / 窗帘五金",
    (
        "Home > Decor > Curtains & Window Treatments > Curtain Hanging Acc"
        "essories > Curtain Tie Backs"
    ): "窗帘配件 / 窗帘绑带",
    ("Home > Decor > Curtains & Window Treatments > Curtain Rods > Shop Curtain Rods"): (
        "窗帘配件 / 窗帘杆"
    ),
    "Home > Decor > Decorative Accents > Decorative Trays": "家居装饰 / 装饰托盘",
    "Home > Decor > Decorative Accents > Knick-Knacks": "家居装饰 / 小摆件",
    "Home > Decor > Decorative Accents > Vases": "家居装饰 / 花瓶",
    "Home > Decor > Rugs > Rug Pads > All Rug Pads & Grippers": "地毯配件 / 防滑垫及固定用品",
    "Home > Decor > Shop All Decor": "家居装饰 / 综合装饰用品",
    "Home > Decor > Slipcovers": "家具防护 / 沙发家具罩",
    "Home > Decor > Wall Art > Metal Wall Art": "墙面装饰 / 金属墙饰",
    "Home > Decor > Wall Decor > Shop All Wall Decor": "墙面装饰 / 墙面装饰用品",
    "Home > Furniture > Living Room Furniture > Recliners > All Recliners": "客厅家具 / 躺椅",
    "Home > Holiday Decor > Christmas Decor > Christmas Trim a Home": "节庆装饰 / 圣诞家居饰品",
    "Home > Kitchen & Dining > Bakeware > Measuring Cups": "厨房烘焙 / 量杯",
    (
        "Home > Kitchen & Dining > Dining & Entertaining > Bar & Wine Accessories > Bar Tools"
    ): "餐酒工具 / 调酒工具",
    ("Home > Kitchen & Dining > Dining & Entertaining > Barware > Moscow Mule Mugs"): (
        "酒具 / 莫斯科骡子铜杯"
    ),
    "Home > Kitchen & Dining > Dining & Entertaining > Drinkware": "餐桌用品 / 饮具",
    ("Home > Kitchen & Dining > Dining & Entertaining > Serveware > Cake Stands"): (
        "餐桌摆设 / 蛋糕架"
    ),
    "Home > Kitchen & Dining > Dining & Entertaining > Serveware > Coasters": "餐桌用品 / 杯垫",
    (
        "Home > Kitchen & Dining > Dining & Entertaining > Serveware > Condiment Servers"
    ): "餐桌用品 / 调味品盛放器",
    "Home > Kitchen & Dining > Fridge Magnets": "厨房用品 / 冰箱贴",
    (
        "Home > Kitchen & Dining > Kitchen Storage & Organization > Pantry Organization"
    ): "厨房收纳 / 食品储藏室整理",
    "Home > Kitchen & Dining > Pots & Pans > Griddles & Grill Pans": "厨房锅具 / 平底煎盘与烤盘",
    ("Home > Kitchen & Dining > Tools & Gadgets > Baking & Pastry Tools"): (
        "厨房烘焙 / 烘焙与糕点工具"
    ),
    "Home > Kitchen & Dining > Tools & Gadgets > Can Openers": "厨房工具 / 开罐器",
    "Home > Kitchen & Dining > Tools & Gadgets > Food Prep": "厨房工具 / 食材预处理工具",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Cheese Slicers"
    ): "厨房工具 / 奶酪切片器",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Chopping & Slicing"
    ): "厨房工具 / 切碎与切片工具",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Cooking Utensils"
    ): "厨房工具 / 烹饪用具",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Food Peelers"
    ): "厨房工具 / 食材削皮器",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Pasta Tools"
    ): "厨房工具 / 意面工具",
    "Home > Luggage > Garment Bags": "旅行箱包 / 衣物防皱袋",
    "Home > Luggage > Travel Accessories > Travel Pillows": "旅行用品 / 旅行枕",
    (
        "Home > Storage & Organization > Closet Organizers > Hanging Closet Organizers"
    ): "衣柜收纳 / 悬挂式衣柜整理器",
    ("Home > Storage & Organization > Laundry Storage & Organization > Drying Racks"): (
        "洗衣收纳 / 晾衣架"
    ),
    "Home > Storage & Organization > Laundry Storage & Organization > Hangers": "洗衣收纳 / 衣架",
    "Home > Storage & Organization > Shop all Storage & Organization": "家居收纳 / 综合收纳用品",
    "Home > Storage & Organization > Storage Baskets & Bins > Baskets": "家居收纳 / 收纳篮",
    ("Home > Storage & Organization > Storage Containers > Shop Storage Containers"): (
        "家居收纳 / 收纳容器"
    ),
    "Home > Storage & Organization > Trash Cans > Shop All Trash Cans": "家居收纳 / 垃圾桶",
    "Home Improvement > Building Materials > Stair Parts": "装修材料 / 楼梯配件",
    (
        "Home Improvement > Doors and Gates > Garage Door Openers and Hard"
        "ware > Garage Door Hardware > All Garage Door Hardware"
    ): "车库五金 / 车库门配件",
    (
        "Home Improvement > Electrical > Cable Management > Zip Ties > Zip"
        " Tie Sizes > 12 Inch Zip Ties"
    ): "电工配件 / 12英寸扎带",
    (
        "Home Improvement > Electrical > Extension Cord Reels > Extension Cord Holders"
    ): "电工配件 / 延长线收纳架",
    "Home Improvement > Emergency Prep > Storm & Flood Prep": "应急防护 / 暴风雨与洪水防护用品",
    (
        "Home Improvement > Hardware > Brackets and Angle Irons > All Brackets and Angle Irons"
    ): "五金连接件 / 支架与角铁",
    ("Home Improvement > Hardware > Door Hardware > Door Locks and Deadbolts"): (
        "门窗五金 / 门锁与锁舌"
    ),
    "Home Improvement > Hardware > Furniture Hardware > Furniture Pads": "家具五金 / 家具防护垫",
    "Home Improvement > Hardware > Hinges > Cabinet Hinges": "铰链五金 / 橱柜铰链",
    "Home Improvement > Hardware > Hinges > Door Hinges": "铰链五金 / 门铰链",
    "Home Improvement > Hardware > Hooks > Coat Hooks": "挂钩五金 / 衣帽挂钩",
    "Home Improvement > Hardware > Hooks > House Hooks": "挂钩五金 / 家用挂钩",
    ("Home Improvement > Hardware > Hooks > Picture Hangers > Picture Hanging Wire"): (
        "挂画配件 / 挂画钢丝"
    ),
    "Home Improvement > Hardware > Hooks > Picture Hangers > Plate Hangers": "挂画配件 / 盘架挂钩",
    (
        "Home Improvement > Heating, Cooling, & Air Quality > Air Quality "
        "> Air Purifier Filters > All Air Purifier Filters"
    ): "空气净化 / 空气净化器滤芯",
    (
        "Home Improvement > Heating, Cooling, & Air Quality > Cooling > Ai"
        "r Conditioners > Air Conditioner Parts & Accessories > All Air Co"
        "nditioner Parts & Accessories"
    ): "空调配件 / 空调零件及附件",
    (
        "Home Improvement > Heating, Cooling, & Air Quality > HVAC Ducting"
        " and Ventilation > Ventilation"
    ): "暖通配件 / 通风用品",
    (
        "Home Improvement > Plumbing > Shop Plumbing by Fixture > Kitchen "
        "Sinks Plumbing > Kitchen Sink Drains"
    ): "厨房水管 / 水槽排水配件",
    (
        "Home Improvement > Plumbing > Shop Plumbing by Fixture > Shower a"
        "nd Bathtub Plumbing > Bathtub Stoppers"
    ): "浴缸水管 / 浴缸排水塞",
    (
        "Home Improvement > Plumbing > Shop Plumbing by Fixture > Shower a"
        "nd Bathtub Plumbing > Shower Traps"
    ): "淋浴水管 / 淋浴排水存水弯",
    (
        "Home Improvement > Plumbing > Shop Plumbing by Fixture > Toilet P"
        "lumbing > Toilet Installation & Repair Tools > Toilet Installatio"
        "n Kits"
    ): "马桶安装 / 马桶安装套件",
    "Home Improvement > Tools > Hand Tools > Scrapers": "手动工具 / 刮刀",
    ("Home Improvement > Tools > Tool Equipment & Storage > Wet"): (
        "工具设备 / 湿用类别（源类目不完整）"
    ),
    "Home Improvement > Weatherproofing > Insulation > Attic Insulation": "保温隔热 / 阁楼隔热材料",
    ("Home Improvement > Weatherproofing > Insulation > Fiberglass Insulation"): (
        "保温隔热 / 玻璃纤维保温棉"
    ),
    (
        "Home Improvement > Windows & Window Supplies > Window Weatherproo"
        "fing > Window Weatherstripping"
    ): "门窗密封 / 窗户密封条",
    (
        "Household Essentials > Cleaning Supplies > Cleaning Tools > Cleaning Refills"
    ): "清洁用品 / 清洁工具替换件",
    (
        "Household Essentials > Cleaning Supplies > Cleaning Tools > Dusters > All Dusters"
    ): "清洁用品 / 除尘掸",
    (
        "Household Essentials > Cleaning Supplies > Cleaning Tools > Spong"
        "es and Scrubbers > Scour Pads"
    ): "清洁用品 / 百洁布与擦洗垫",
    "Household Essentials > Cleaning Supplies > Mops > All Mops": "清洁用品 / 拖把",
    ("Household Essentials > Paper & Plastic > Food Storage Bags > Food Bags"): (
        "食品包装 / 食品保鲜袋"
    ),
    (
        "Industrial & Scientific > Food Service Equipment & Supplies > Foo"
        "d Holding and Warming Equipment > Steam Tables and Food Wells"
    ): "商用餐饮 / 保温餐台与水浴保温槽",
    (
        "Industrial & Scientific > Janitorial & Sanitation Supplies > Jani"
        "torial Disposables > Commercial Toilet Paper Dispensers & Holders"
    ): "商用清洁 / 卫生纸分配器及支架",
    (
        "Industrial & Scientific > Janitorial & Sanitation Supplies > Odor"
        " Maintainers > Commercial Air Fresheners & Deodorizers"
    ): "商用清洁 / 空气清新及除臭用品",
    "Industrial & Scientific > Store Fixtures & Equipment > Display Cases": "商用设备 / 展示柜",
    (
        "Musical Instruments > Instrument Accessories > String Instrument Accessories > Stands"
    ): "乐器配件 / 弦乐器支架",
    "Office Supplies > Desk Organization > File Organizers": "办公收纳 / 文件整理架",
    ("Office Supplies > Labels & Label Makers > Labels > All Labels & Stickers"): (
        "办公文具 / 标签与贴纸"
    ),
    "Office Supplies > School Supplies > Shop All School Supplies": "学校用品 / 综合学习用品",
    "Office Supplies > Shop All Office Supplies": "办公用品 / 综合办公用品",
    (
        "Party & Occasions > Birthday Shop > Birthday Party Supplies > Birthday Hanging Decorations"
    ): "生日派对 / 悬挂装饰",
    (
        "Party & Occasions > Birthday Shop > Birthday Party Supplies > Birthday Party Decorations"
    ): "生日派对 / 派对装饰",
    ("Party & Occasions > Carnival Party Supplies > Carnival Party Decorations"): (
        "嘉年华派对 / 装饰用品"
    ),
    (
        "Party & Occasions > Christmas Trees & Christmas Decor > Christmas"
        " Decor > Christmas Wreaths > Outdoor Christmas Wreaths"
    ): "圣诞装饰 / 户外圣诞花环",
    (
        "Party & Occasions > Party Supplies > Party Supplies by Color > Gr"
        "een Party Supplies > Green Party Decorations"
    ): "派对装饰 / 绿色主题装饰",
    (
        "Party & Occasions > Party Supplies > Party Supplies by Color > Me"
        "tallic Party Supplies > Metallic Party Decorations"
    ): "派对装饰 / 金属色主题装饰",
    ("Party & Occasions > Wedding Shop > The Wedding Day > Ceremony Essentials"): (
        "婚礼用品 / 婚礼仪式用品"
    ),
    ("Patio & Garden > Clearance Patio & Garden > Clearance Outdoor Lighting"): (
        "庭院照明 / 特价户外灯具"
    ),
    "Patio & Garden > Decorative Stones": "庭院园艺 / 装饰石",
    "Patio & Garden > Garden Center > Pots & Planters > Garden Planters": "花盆花器 / 园艺种植盆",
    (
        "Patio & Garden > Garden Center > Pots & Planters > Outdoor Planters > Hanging Planters"
    ): "花盆花器 / 户外吊挂花盆",
    "Patio & Garden > Garden Center > Pots & Planters > Plant Stands": "花盆花器 / 花架",
    "Patio & Garden > Garden Center > Watering & Irrigation > Hose Nozzles": "园艺浇灌 / 水管喷头",
    (
        "Patio & Garden > Outdoor Power Equipment > Outdoor Power Equipmen"
        "t Parts and Accessories > Pressure Washer Accessories > Pressure "
        "Washer Fittings"
    ): "高压清洗 / 高压清洗机接头",
    (
        "Patio & Garden > Sheds & Outdoor Storage > Patio Furniture Covers"
        " > Waterproof Outdoor Furniture Covers"
    ): "庭院家具 / 防水家具罩",
    "Patio & Garden > Wild Bird Supplies > Bird Feeders > Ground Feeders": "野鸟用品 / 地面喂鸟器",
    "Personal Care > Clear Bags > Clear Makeup Bags": "美妆收纳 / 透明化妆包",
    "Pets > Cats > Cat Beds > All Cat Beds": "猫用品 / 猫窝",
    "Pets > Dogs > Dog Bowls and Accessories > Dog Bowls and Feeders": "狗用品 / 狗食盆与喂食器",
    ("Pets > Dogs > Dog Collars, Leashes, and Harnesses > No Pull Dog Harnesses"): (
        "狗用品 / 防暴冲胸背带"
    ),
    "Pets > Dogs > Dog Toys > All Dog Toys": "狗用品 / 狗玩具",
    "Pets > Fish Supplies > Fish Tank Decoration > Aquarium Plants": "水族用品 / 鱼缸造景水草",
    (
        "Sports & Outdoors > Exercise & Fitness > Treadmills > Treadmill A"
        "ccessories > All Treadmill Accessories"
    ): "跑步机配件 / 跑步机零配件",
    "Sports & Outdoors > Exercise & Fitness > Yoga > Yoga Blocks": "瑜伽用品 / 瑜伽砖",
    (
        "Sports & Outdoors > Recreation > Game Room > Pool & Billiards > C"
        "ue Sticks > All Pool and Billiard Sticks"
    ): "台球用品 / 台球杆",
    ("Sports & Outdoors > Sports > Tennis & Racquets > Tennis Training Aids"): (
        "网球用品 / 网球训练辅助器"
    ),
    ("Toys > Action Figures and Playsets > Action Figures > Action Figure Core"): (
        "玩具手办 / 可动人偶"
    ),
    "Toys > Arts & Crafts for Kids > Kid Art Easels & Stations": "儿童手工 / 儿童画架",
    "Toys > Bikes > Bike Accessories > Bike Bags & Carriers": "儿童骑行 / 自行车包与置物架",
    "Toys > Bikes > Bike Accessories > Bike Baskets": "儿童骑行 / 自行车车篮",
    "Toys > Games & Puzzles > Classic Games": "玩具游戏 / 经典桌面游戏",
    ("Walmart for Business > Retail Essentials > Pricemaking Supplies > Price Guns"): (
        "零售设备 / 标价枪"
    ),
}

_V6_EXACT_CATEGORY_PATH_ZH = {
    (
        "Arts Crafts & Sewing > Art Supplies > Art Painting Supplies > Shop Art Painting Supplies"
    ): "手工艺用品 / 选购绘画用品",
    "Arts Crafts & Sewing > Art Supplies > Shop Art Supplies": "手工艺用品 / 选购美术用品",
    (
        "Arts Crafts & Sewing > Arts & Crafts Furniture and Storage > Artist Easels > Wooden Easels"
    ): "手工艺用品 / 木质画架",
    (
        "Arts Crafts & Sewing > Arts & Crafts Furniture and Storage > Craf"
        "t Storage > Art and Poster Tubes"
    ): "手工艺用品 / 画作与海报收纳筒",
    (
        "Arts Crafts & Sewing > Arts & Crafts Furniture and Storage > Craf"
        "t Storage > Sewing Storage > Thread and Fabric Storage"
    ): "手工艺用品 / 线材与布料收纳",
    "Arts Crafts & Sewing > Beading & Jewelry Making > Beads > Spacer Beads": "手工艺用品 / 隔珠",
    (
        "Arts Crafts & Sewing > Crafting > Craft Supplies > Basic Craft Supplies > Craft Shells"
    ): "手工艺用品 / 手工贝壳材料",
    ("Arts Crafts & Sewing > Crafting > Paper Crafting > Junk Journal Supplies"): (
        "手工艺用品 / 拼贴手账材料"
    ),
    (
        "Arts Crafts & Sewing > Crafting > Shop All Arts & Craft Kits > Art & Craft Kits"
    ): "手工艺用品 / 美术与手工套装",
    (
        "Arts Crafts & Sewing > Crafting > Speciality Crafts & Hobbies > F"
        "loral Arranging > All Floral Arranging Supplies"
    ): "手工艺用品 / 全部插花用品",
    ("Arts Crafts & Sewing > Die Cutting > Craft Vinyl > Shop All Craft Vinyl"): (
        "手工艺用品 / 全部手工刻字贴膜"
    ),
    "Arts Crafts & Sewing > Die Cutting > Shop All Die Cutting": "手工艺用品 / 全部模切用品",
    "Arts Crafts & Sewing > Die Cutting > Transfer Papers": "手工艺用品 / 转印纸",
    "Arts Crafts & Sewing > Resin > Resin Molds": "手工艺用品 / 树脂模具",
    "Arts Crafts & Sewing > Scrapbooking > Stencils & Templates": "手工艺用品 / 镂空模板与样板",
    (
        "Arts Crafts & Sewing > Sewing > Fills, Foam and Pillow Forms > Sh"
        "op Fills, Foam and Pillows"
    ): "手工艺用品 / 全部填充材料、泡棉与抱枕芯",
    ("Arts Crafts & Sewing > Sewing > Notions & Sewing Accessories > Bobbins"): (
        "手工艺用品 / 缝纫机梭芯"
    ),
    "Arts Crafts & Sewing > Sewing > Sewing & Cutting Tools > Cutting Mats": "手工艺用品 / 切割垫",
    (
        "Arts Crafts & Sewing > Yarn & Needle Arts > Needle Arts > Embroid"
        "ery > Embroidery Floss & Thread > Floss Organizer Sets"
    ): "手工艺用品 / 绣线收纳套装",
    (
        "Auto & Tires > Auto Body > Auto Paint Tools > Auto Sandpaper and Abrasives"
    ): "汽车用品 / 汽车打磨砂纸与磨料",
    ("Auto & Tires > Automotive Paint > Interior Repair & Restoration"): (
        "汽车用品 / 汽车内饰维修与修复"
    ),
    "Auto & Tires > Automotive Tools & Equipment > Automotive Electrical": "汽车用品 / 汽车电气",
    (
        "Auto & Tires > Automotive Tools & Equipment > Automotive Stands a"
        "nd Supports > Jack Accessories > Jack Pads"
    ): "汽车用品 / 千斤顶支撑垫",
    (
        "Auto & Tires > Automotive Tools & Equipment > Garage and Shop > G"
        "arage Roller Seats And Creepers"
    ): "汽车用品 / 车库维修滑轮凳与躺板",
    (
        "Auto & Tires > Car Detailing > Car Wash Supplies > Car Polishing "
        "Pads > 6 Inch Polishing Pads"
    ): "汽车用品 / 6英寸抛光垫",
    (
        "Auto & Tires > Car Detailing > Car Wash Supplies > Car Wash Brush"
        "es > Car Wash Brush with Handle"
    ): "汽车用品 / 带手柄洗车刷",
    (
        "Auto & Tires > Car Detailing > Car Wash Supplies > Car Wash Mitts > Microfiber Wash Mitts"
    ): "汽车用品 / 超细纤维洗车手套",
    "Auto & Tires > Car Detailing > Car Wash Supplies > Car Wash Sponges": "汽车用品 / 洗车海绵",
    (
        "Auto & Tires > EV Parts & Accessories > EV Chargers > EV Chargers"
        " by Type > Electric Vehicle Supply Equipment (EVSE)"
    ): "汽车用品 / 电动汽车供电设备",
    (
        "Auto & Tires > Exterior Car Parts & Accessories > Mud Flaps & Splash Guards > Mud Flaps"
    ): "汽车用品 / 汽车挡泥板",
    (
        "Auto & Tires > Exterior Car Parts & Accessories > Truck Bed Acces"
        "sories > Truck Bed Organizers"
    ): "汽车用品 / 皮卡车货箱收纳用品",
    (
        "Auto & Tires > Exterior Car Parts & Accessories > Truck Bed Acces"
        "sories > Truck Bed Rail Caps"
    ): "汽车用品 / 皮卡车货箱栏板盖条",
    (
        "Auto & Tires > Interior Parts & Accessories > Car Organizers > Car Console Organizers"
    ): "汽车用品 / 汽车中控台收纳用品",
    ("Auto & Tires > Interior Parts & Accessories > Car Organizers > Car Trash Cans"): (
        "汽车用品 / 车载垃圾桶"
    ),
    (
        "Auto & Tires > Interior Parts & Accessories > Car Organizers > Cl"
        "othes Hanging Rods for Cars"
    ): "汽车用品 / 车用挂衣杆",
    (
        "Auto & Tires > Interior Parts & Accessories > Car Seat Covers > C"
        "ar Seat Covers by Feature > Universal Seat Covers"
    ): "汽车用品 / 通用座椅套",
    (
        "Auto & Tires > Powersport Parts & Accessories > Dirt Bike Parts &"
        " Accessories > Dirt Bike Parts > Dirt Bike Hand Controls > Dirt B"
        "ike Handlebar Crossbars"
    ): "汽车用品 / 越野摩托车车把横杆",
    ("Auto & Tires > RV Parts & Accessories > RV Levelers > All RV Levelers"): (
        "汽车用品 / 全部房车调平器"
    ),
    (
        "Auto & Tires > RV Parts & Accessories > RV Waste Water and Sanita"
        "tion > RV Water Filters > All RV Water Filters"
    ): "汽车用品 / 全部房车净水滤芯",
    (
        "Auto & Tires > Wheel Accessories > Lug Nuts, Lug Nut Covers & Lug"
        " Nut Keys > Lug Nuts & Lug Nut Sets"
    ): "汽车用品 / 车轮螺母与套装",
    "Baby > Diapering > Diaper Organizers > Diaper Caddy": "母婴用品 / 尿布收纳篮",
    "Baby > Diapering > Potty Training > Potties": "母婴用品 / 儿童便盆",
    "Baby > Diapering > Wipe Warmers & Holders > Baby Wipe Dispenser": "母婴用品 / 婴儿湿巾盒",
    "Baby > Feeding > Bottle Feeding": "母婴用品 / 奶瓶喂养",
    "Baby > Nursery & Decor > Baby Decor > Crib Mobiles": "母婴用品 / 婴儿床旋转挂饰",
    (
        "Baby > Nursery & Decor > Nursery Storage and Organizers > All Nursery Storage"
    ): "母婴用品 / 全部婴儿房收纳用品",
    ("Beauty > Hair Care > Hair Accessories > Hair Tools & Accessories Combined"): (
        "美妆个护 / 美发工具及配件"
    ),
    "Beauty > Makeup > Makeup Tools & Brushes > Cosmetic Cottons > Cotton Swabs": "美妆个护 / 棉签",
    "Clothing > Bags & Accessories > Handbags > Clear Bags": "服饰配件 / 透明包袋",
    ("Clothing > Womens Clothing > Womens Coats > Womens Faux Fur Coats"): (
        "服饰配件 / 女士仿皮草外套"
    ),
    ("Collectibles > Trading Cards > Trading Card Binders & Sleeves"): (
        "收藏卡牌 / 收藏卡活页夹与保护套"
    ),
    (
        "Electronics > Computers, Laptops and Tablets > Computer Accessori"
        "es > Blank Media > Blank Media"
    ): "电子数码 / 空白存储介质",
    (
        "Electronics > Electronics Accessories > General Electronic Access"
        "ories > All Electronics Carrying Cases"
    ): "电子数码 / 全部电子设备收纳包",
    ("Electronics > TV & Home Theater > TV Accessories > TV Cables & Connectors"): (
        "电子数码 / 电视线缆与连接器"
    ),
    (
        "Electronics > Walmart Restored > Restored Home > Walmart Restored"
        " Cooling and Heating > All Walmart Restored Cooling and Heating"
    ): "电子数码 / 全部沃尔玛翻新制冷与供暖设备",
    (
        "Electronics > Walmart Restored > Restored Home > Walmart Restored"
        " Small Appliances > All Walmart Restored Small Appliances"
    ): "电子数码 / 全部沃尔玛翻新小家电",
    (
        "Food > Baking > Baking Ingredients > Frosting, Toppings & Decorat"
        "ions > All Frosting, Toppings, & Decorations"
    ): "食品杂货 / 全部糖霜、配料与烘焙装饰",
    (
        "Food > Baking > Baking Ingredients > Frosting, Toppings & Decorations > Baking Decorations"
    ): "食品杂货 / 烘焙装饰用品",
    "Health and Medicine > Foot Care > Insoles > Shop All Insoles": "健康护理 / 全部鞋垫",
    (
        "Health and Medicine > Home Health Care > Daily Living Aids > Shop all Daily Living Aids"
    ): "健康护理 / 全部日常生活辅助用品",
    ("Health and Medicine > Home Health Care > Medical Supplies & Equipment"): (
        "健康护理 / 医疗用品与设备"
    ),
    ("Home > Appliances > Appliances Parts & Accessories > Appliance Belts"): (
        "家用电器 / 家电传动皮带"
    ),
    "Home > Appliances > Appliances Parts & Accessories > Appliance Handles": "家用电器 / 家电把手",
    (
        "Home > Appliances > Appliances Parts & Accessories > Dishwasher P"
        "arts > Dishwasher Baskets & Racks"
    ): "家用电器 / 洗碗机篮筐与碗架",
    (
        "Home > Appliances > Appliances Parts & Accessories > Refrigerator"
        " & Freezer Parts > Refrigerator Bins"
    ): "家用电器 / 冰箱收纳盒",
    "Home > Appliances > Kitchen Appliances > Fryers > Deep Fryers": "厨房用品 / 油炸锅",
    "Home > Bath > Bath Towels > Bath Towel Sets": "浴室用品 / 浴巾套装",
    "Home > Bath > Bath Towels > Hand Towels": "浴室用品 / 擦手巾",
    "Home > Bath > Bathroom Accessories > Bathroom Soap Dispenser Set": "浴室用品 / 浴室皂液器套装",
    "Home > Bath > Bathroom Sets": "浴室用品 / 浴室用品套装",
    ("Home > Bedding > Mattress Covers & Protectors > Fitted Mattress Protectors"): (
        "床上用品 / 床垫保护套"
    ),
    "Home > Decor > Blinds & Shades > Blinds > Door Blinds": "家居装饰 / 门用百叶帘",
    "Home > Decor > Candles & Home Fragrance > Glass Candle Holders": "家居装饰 / 玻璃烛台",
    (
        "Home > Decor > Curtains & Window Treatments > Curtain Hanging Acc"
        "essories > Drapery & Curtain Hooks"
    ): "家居装饰 / 窗帘挂钩",
    "Home > Decor > Decorative Accents > Decorative Balls": "家居装饰 / 装饰球",
    "Home > Decor > Decorative Accents > Decorative Bowls": "家居装饰 / 装饰碗",
    "Home > Decor > Decorative Accents > Decorative Boxes": "家居装饰 / 装饰盒",
    "Home > Decor > Decorative Accents > Suncatchers": "家居装饰 / 捕光挂饰",
    (
        "Home > Decor > Decorative Pillows & Throws > Decorative Pillows & Throws Shop All"
    ): "家居装饰 / 全部装饰抱枕与盖毯",
    "Home > Decor > Wall Art > Framed Wall Art": "家居装饰 / 装框墙面装饰画",
    "Home > Decor > Wall Decor > Shadow Boxes": "家居装饰 / 立体展示框",
    "Home > Decor > Wall Decor > Wall Hangings > Macrame Wall Hangings": "家居装饰 / 绳编墙饰",
    "Home > Decor > Wall Decor > Wall Shelves > Floating Shelves": "家居装饰 / 悬浮置物架",
    "Home > Decor > Wall Decor > Wall Shelves > Wood Floating Shelves": "家居装饰 / 木质悬浮置物架",
    ("Home > Furniture > Bedroom Furniture > Nightstands > 3 Drawer Nightstand"): (
        "家具用品 / 三抽屉床头柜"
    ),
    "Home > Furniture > Entryway Furniture > Coat Racks": "家具用品 / 衣帽架",
    "Home > Furniture > Entryway Furniture > Umbrella Racks & Stands": "家具用品 / 雨伞架",
    ("Home > Furniture > Kitchen & Dining Furniture > Kitchen Islands & Carts"): (
        "家具用品 / 厨房中岛与推车"
    ),
    ("Home > Furniture > Living Room Furniture > Coffee Tables > Wood Coffee Tables"): (
        "家具用品 / 木质茶几"
    ),
    ("Home > Furniture > Living Room Furniture > End Tables > Wood End Tables"): (
        "家具用品 / 木质边几"
    ),
    "Home > Furniture > TV Stands & Entertainment Centers > TV Stands": "家具用品 / 电视柜",
    "Home > Holiday Decor > Fall Decor > Fall Indoor Decor": "家居装饰 / 秋季室内装饰",
    (
        "Home > Holiday Decor > Halloween Decor > Indoor Halloween Decor > Halloween Tabletop Decor"
    ): "家居装饰 / 万圣节餐桌装饰",
    "Home > Kids' Rooms > Kids' Furniture > Shop All Kids' Furniture": "儿童家居 / 全部儿童家具",
    ("Home > Kids' Rooms > Kids' Room Decor > Kids' Wall Decals & Stickers"): (
        "儿童家居 / 儿童墙贴与装饰贴纸"
    ),
    "Home > Kitchen & Dining > Bakeware > Bakeware Sets": "厨房用品 / 烘焙器具套装",
    "Home > Kitchen & Dining > Bakeware > Baking & Cookie Sheets": "厨房用品 / 烘焙烤盘与饼干烤盘",
    "Home > Kitchen & Dining > Bakeware > Baking Dishes": "厨房用品 / 烘焙烤皿",
    "Home > Kitchen & Dining > Bakeware > Cake & Bundt Pans": "厨房用品 / 蛋糕烤模与环形蛋糕模",
    "Home > Kitchen & Dining > Bakeware > Pizza Stones & Pans": "厨房用品 / 披萨烤石与烤盘",
    "Home > Kitchen & Dining > Bakeware > Shop Bakeware": "厨房用品 / 全部烘焙器具",
    "Home > Kitchen & Dining > Bowls > Shop Bowls": "厨房用品 / 全部碗具",
    "Home > Kitchen & Dining > Cutting Boards > All Cutting Boards": "厨房用品 / 全部砧板",
    (
        "Home > Kitchen & Dining > Dining & Entertaining > Bar & Wine Accessories > Koozies"
    ): "厨房用品 / 饮料保冷杯套",
    (
        "Home > Kitchen & Dining > Dining & Entertaining > Bar & Wine Acce"
        "ssories > Shop All Bar & Wine Accessories"
    ): "厨房用品 / 全部酒吧与葡萄酒配件",
    (
        "Home > Kitchen & Dining > Dining & Entertaining > Bar & Wine Acce"
        "ssories > Wine Aerators & Pourers"
    ): "厨房用品 / 葡萄酒醒酒器与倒酒器",
    (
        "Home > Kitchen & Dining > Dining & Entertaining > Barware > Beer & Wine Glasses"
    ): "厨房用品 / 啤酒杯与葡萄酒杯",
    ("Home > Kitchen & Dining > Dining & Entertaining > Drinkware > Coffee Mugs"): (
        "厨房用品 / 咖啡杯"
    ),
    (
        "Home > Kitchen & Dining > Dining & Entertaining > Drinkware > Drinking Glasses"
    ): "厨房用品 / 饮用玻璃杯",
    ("Home > Kitchen & Dining > Dining & Entertaining > Drinkware Accessories"): (
        "厨房用品 / 饮具配件"
    ),
    (
        "Home > Kitchen & Dining > Dining & Entertaining > Flatware > Flatware Serving Utensils"
    ): "厨房用品 / 分餐用刀叉勺",
    (
        "Home > Kitchen & Dining > Dining & Entertaining > Serveware > Pitchers & Carafes"
    ): "厨房用品 / 冷水壶与玻璃分享壶",
    (
        "Home > Kitchen & Dining > Dining & Entertaining > Serveware > Salt & Pepper Shakers"
    ): "厨房用品 / 盐与胡椒调味罐",
    (
        "Home > Kitchen & Dining > Dining & Entertaining > Serveware > Serving Platters & Trays"
    ): "厨房用品 / 餐盘与托盘",
    (
        "Home > Kitchen & Dining > Dining & Entertaining > Serveware > Sugar Bowls & Creamers"
    ): "厨房用品 / 糖罐与奶盅",
    (
        "Home > Kitchen & Dining > Dining & Entertaining > Travel Drinkwar"
        "e > Water Bottles > Kids' Water Bottles"
    ): "厨房用品 / 儿童水壶",
    (
        "Home > Kitchen & Dining > Kitchen & Table Linens > Table Linens > Chair Sashes"
    ): "厨房用品 / 椅背装饰带",
    ("Home > Kitchen & Dining > Kitchen & Table Linens > Table Linens > Placemats"): (
        "厨房用品 / 餐垫"
    ),
    ("Home > Kitchen & Dining > Kitchen & Table Linens > Table Linens > Table Runners"): (
        "厨房用品 / 桌旗"
    ),
    ("Home > Kitchen & Dining > Kitchen & Table Linens > Table Linens > Tablecloths"): (
        "厨房用品 / 桌布"
    ),
    (
        "Home > Kitchen & Dining > Kitchen Storage & Organization > Counter Organizers"
    ): "厨房用品 / 厨房台面收纳用品",
    (
        "Home > Kitchen & Dining > Kitchen Storage & Organization > Dinnerware & Serving Storage"
    ): "厨房用品 / 餐具与上菜器皿收纳",
    (
        "Home > Kitchen & Dining > Kitchen Storage & Organization > Food S"
        "torage Containers > Glass Storage Containers"
    ): "厨房用品 / 玻璃收纳容器",
    (
        "Home > Kitchen & Dining > Kitchen Storage & Organization > Food S"
        "torage Containers > Hunting Food Storage"
    ): "厨房用品 / 狩猎食品储存用品",
    (
        "Home > Kitchen & Dining > Kitchen Storage & Organization > Food S"
        "torage Containers > Kitchen Canisters"
    ): "厨房用品 / 厨房储物罐",
    (
        "Home > Kitchen & Dining > Kitchen Storage & Organization > Food S"
        "torage Containers > Shop All Food Storage Containers"
    ): "厨房用品 / 全部食品保鲜容器",
    (
        "Home > Kitchen & Dining > Kitchen Storage & Organization > Kitchen Drawer Organizers"
    ): "厨房用品 / 厨房抽屉收纳用品",
    ("Home > Kitchen & Dining > Kitchen Storage & Organization > Mason Jars"): (
        "厨房用品 / 梅森玻璃罐"
    ),
    (
        "Home > Kitchen & Dining > Kitchen Storage & Organization > Pot Racks & Organizers"
    ): "厨房用品 / 锅具置物架与整理架",
    ("Home > Kitchen & Dining > Kitchen Storage & Organization > Sink Accessories"): (
        "厨房用品 / 水槽配件"
    ),
    "Home > Kitchen & Dining > Kitchen Storage & Organization > Spice Racks": "厨房用品 / 调味料架",
    "Home > Kitchen & Dining > Kitchen Storage & Organization > Wine Racks": "厨房用品 / 酒架",
    "Home > Kitchen & Dining > Pots & Pans > Frying Pans & Skillets": "厨房用品 / 煎锅和平底锅",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Avocado Slicers"
    ): "厨房用品 / 牛油果切片器",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Bag & Chip Clips"
    ): "厨房用品 / 包装袋与零食封口夹",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Batter Dispensers"
    ): "厨房用品 / 面糊分配器",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Burger Press"
    ): "厨房用品 / 汉堡肉饼压模",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Egg Slicers"
    ): "厨房用品 / 鸡蛋切片器",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Food Choppers"
    ): "厨房用品 / 食物切碎器",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Food Thermometers"
    ): "厨房用品 / 食物温度计",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadge"
        "ts > Fruit & Vegetable Tools"
    ): "厨房用品 / 水果与蔬菜工具",
    ("Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Graters"): (
        "厨房用品 / 刨丝器"
    ),
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Kitchen Spatulas"
    ): "厨房用品 / 厨房铲勺",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Lemon Squeezer"
    ): "厨房用品 / 柠檬榨汁器",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Meat Tools"
    ): "厨房用品 / 肉类处理工具",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadge"
        "ts > Potato Mashers & Ricers"
    ): "厨房用品 / 土豆捣泥器与压泥器",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Salad Spinners"
    ): "厨房用品 / 沙拉甩干篮",
    (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadge"
        "ts > Turkey & Meat Basters"
    ): "厨房用品 / 火鸡及肉类浇汁器",
    "Home > Kitchen & Dining > Tools & Gadgets > Tea Kettles": "厨房用品 / 茶壶",
    "Home > Luggage > Carry On Luggage": "旅行用品 / 随身登机箱",
    "Home > Luggage > Duffel Bags": "旅行用品 / 旅行圆筒包",
    "Home > Luggage > Travel Accessories > Luggage Racks": "旅行用品 / 行李架",
    "Home > Luggage > Travel Accessories > Packing Cubes": "旅行用品 / 行李收纳袋",
    "Home > Luggage > Travel Accessories > Toiletry Bags": "旅行用品 / 洗漱包",
    "Home > Luggage > Travel Accessories > Travel Wallets": "旅行用品 / 旅行证件钱包",
    ("Home > Storage & Organization > Closet Organizers > Clothes Protectors"): (
        "家居收纳 / 衣物防护罩"
    ),
    ("Home > Storage & Organization > Closet Organizers > shoe storage > Shoe Racks"): (
        "家居收纳 / 鞋架"
    ),
    ("Home > Storage & Organization > Laundry Storage & Organization > Laundry Bags"): (
        "家居收纳 / 洗衣袋"
    ),
    (
        "Home > Storage & Organization > Laundry Storage & Organization > Laundry Hampers"
    ): "家居收纳 / 脏衣篮",
    (
        "Home > Storage & Organization > Laundry Storage & Organization > Wicker Laundry Baskets"
    ): "家居收纳 / 藤编洗衣篮",
    (
        "Home > Storage & Organization > Storage Baskets & Bins > Shop All Storage Baskets & Bins"
    ): "家居收纳 / 全部收纳篮与收纳箱",
    "Home > Storage & Organization > Storage Baskets & Bins > Wood Crates": "家居收纳 / 木箱",
    (
        "Home > Storage & Organization > Storage Containers > Plastic Stor"
        "age Bins & Boxes > Clear Storage Bins"
    ): "家居收纳 / 透明收纳箱",
    "Home > Teens' Rooms > Teens' Bathroom": "儿童家居 / 青少年浴室用品",
    (
        "Home Improvement > Bathroom Renovation > Bathroom Cabinets & Fixt"
        "ures > Corner Shower Shelves"
    ): "水暖卫浴 / 淋浴房转角置物架",
    (
        "Home Improvement > Bathroom Renovation > Bathroom Cabinets & Fixtures > Medicine Cabinets"
    ): "水暖卫浴 / 医药柜",
    (
        "Home Improvement > Bathroom Renovation > Bathroom Cabinets & Fixtures > Shower Shelving"
    ): "水暖卫浴 / 淋浴置物架",
    (
        "Home Improvement > Bathroom Renovation > Bathroom Hardware > Hand Towel Holders"
    ): "水暖卫浴 / 擦手巾架",
    (
        "Home Improvement > Bathroom Renovation > Bathroom Hardware > Toilet Paper Holders"
    ): "水暖卫浴 / 卫生纸架",
    "Home Improvement > Bathroom Renovation > Bathroom Hardware > Towel Racks": "水暖卫浴 / 毛巾架",
    (
        "Home Improvement > Bathroom Renovation > Bathroom Plumbing > Plum"
        "bing Parts and Repairs > Drains"
    ): "水暖卫浴 / 排水配件",
    "Home Improvement > Electrical > Cable Management > Cable Concealer": "五金工具 / 线缆隐藏槽",
    (
        "Home Improvement > Electrical > Cable Management > Zip Ties > Heavy Duty Zip Ties"
    ): "五金工具 / 重型扎带",
    (
        "Home Improvement > Electrical > Cable Management > Zip Ties > Zip"
        " Tie Colors > White Zip Ties"
    ): "五金工具 / 白色扎带",
    (
        "Home Improvement > Electrical > Cable Management > Zip Ties > Zip"
        " Tie Sizes > 8 Inch Zip Ties"
    ): "五金工具 / 8英寸扎带",
    (
        "Home Improvement > Electrical > Dimmers, Switches, and Wall Plate"
        "s > Wall Plates > Outlet Wall Plates"
    ): "五金工具 / 插座面板",
    "Home Improvement > Emergency Prep > Wildfire Prep": "家居装修 / 野火应急用品",
    "Home Improvement > Flooring > Flooring Shims & Spacers": "家居装修 / 地板安装垫片与间隔件",
    ("Home Improvement > Garage Storage > Wall Organization > Pegboard Hooks"): (
        "家居装修 / 洞洞板挂钩"
    ),
    "Home Improvement > Hardware > Door Hardware > All Door Hardware": "五金工具 / 全部门用五金",
    (
        "Home Improvement > Hardware > Door Hardware > Entry Door Hardware > Door Closers"
    ): "五金工具 / 闭门器",
    (
        "Home Improvement > Hardware > Fasteners > Bolts > Round Head Bolt"
        "s > Shop all Round Head Bolts"
    ): "五金工具 / 全部圆头螺栓",
    "Home Improvement > Hardware > Furniture Hardware > Door Stops": "五金工具 / 门挡",
    "Home Improvement > Hardware > Furniture Hardware > Furniture Legs": "五金工具 / 家具腿",
    "Home Improvement > Heating, Cooling, & Air Quality > Water Heaters": "家居装修 / 热水器",
    ("Home Improvement > Ladders and Step Stools > Step Stools > All Step Stools"): (
        "家居装修 / 全部踏脚凳"
    ),
    (
        "Home Improvement > Paint > Paint Supplies & Tools > Hardware Tape > Waterproof Tape"
    ): "家居装修 / 防水胶带",
    ("Home Improvement > Paint > Paint Supplies & Tools > Sandpaper and Abrasives"): (
        "家居装修 / 砂纸与磨料"
    ),
    (
        "Home Improvement > Plumbing > Shop Plumbing by Fixture > Bathroom"
        " Sink Plumbing > Bathroom Sink Drains"
    ): "水暖卫浴 / 浴室洗手盆排水配件",
    (
        "Home Improvement > Plumbing > Shop Plumbing by Fixture > Shower a"
        "nd Bathtub Plumbing > Shower Cartridges"
    ): "水暖卫浴 / 淋浴阀芯",
    (
        "Home Improvement > Plumbing > Shop Plumbing by Fixture > Toilet P"
        "lumbing > Bidet & Washlet Accessories > Bidet Sprayers"
    ): "水暖卫浴 / 冲洗喷枪",
    (
        "Home Improvement > Tools > Air Tools > Air Compressors > Air Compressor Accessories"
    ): "五金工具 / 空气压缩机配件",
    "Home Improvement > Tools > Hand Tools > Chalk Lines and Reels": "五金工具 / 墨斗线与卷线器",
    "Home Improvement > Tools > Hand Tools > Hammers > Mallets": "五金工具 / 木槌与橡胶锤",
    (
        "Home Improvement > Tools > Hand Tools > Ratchets & Sockets > Ratc"
        "het & Socket Combination Sets"
    ): "五金工具 / 棘轮扳手与套筒组合套装",
    "Home Improvement > Tools > Hand Tools > Sharpeners": "五金工具 / 磨刀器与磨具",
    "Home Improvement > Tools > Mechanics Tools": "五金工具 / 机械维修工具",
    ("Home Improvement > Tools > Personal Protective Equipment > Safety Glasses"): (
        "五金工具 / 安全防护眼镜"
    ),
    (
        "Home Improvement > Tools > Power Tool Accessories > Drill Bits > All Drill Bits"
    ): "五金工具 / 全部钻头",
    (
        "Home Improvement > Tools > Power Tool Accessories > Power Saw Acc"
        "essories > Saw Blades > Circular Saw Blades"
    ): "五金工具 / 圆锯片",
    (
        "Home Improvement > Tools > Power Tool Accessories > Power Saw Acc"
        "essories > Saw Blades > Reciprocating Saw Blades"
    ): "五金工具 / 往复锯片",
    "Home Improvement > Tools > Power Tools > Power Saws > Jigsaws": "五金工具 / 曲线锯",
    (
        "Home Improvement > Tools > Tool Equipment & Storage > Dollies & Hand Trucks > Hand Trucks"
    ): "五金工具 / 手推搬运车",
    (
        "Home Improvement > Weatherproofing > Door Weatherproofing > Door Weatherstripping"
    ): "家居装修 / 门缝密封条",
    ("Home Improvement > Windows & Window Supplies > Window Screens and Films"): (
        "家居装修 / 窗纱与玻璃贴膜"
    ),
    "Household Essentials > Bathroom Cleaning Supplies > Toilet Brushes": "清洁用品 / 马桶刷",
    "Household Essentials > Cleaning Supplies > Brooms > Brooms": "清洁用品 / 扫帚",
    (
        "Household Essentials > Cleaning Supplies > Cleaning Tools > Clean"
        "ing Brushes > Dish Brushes"
    ): "清洁用品 / 洗碗刷",
    (
        "Household Essentials > Cleaning Supplies > Cleaning Tools > Clean"
        "ing Brushes > Soap Dispensing Brushes"
    ): "清洁用品 / 可加洗洁精的刷子",
    (
        "Household Essentials > Cleaning Supplies > Cleaning Tools > Spong"
        "es and Scrubbers > Melamine Sponges"
    ): "清洁用品 / 纳米清洁海绵",
    (
        "Household Essentials > Cleaning Supplies > Cleaning Tools > Spong"
        "es and Scrubbers > Steel Wool"
    ): "清洁用品 / 钢丝绒清洁球",
    ("Household Essentials > Cleaning Supplies > Cleaning Tools > Spray Bottles"): (
        "清洁用品 / 喷雾瓶"
    ),
    "Household Essentials > Laundry > Dryer Sheets > Wool Dryer Balls": "家居日用 / 羊毛烘干球",
    (
        "Household Essentials > Paper & Plastic > Disposable Tableware > Disposable Bowls"
    ): "家居日用 / 一次性碗",
    (
        "Household Essentials > Paper & Plastic > Disposable Tableware > Disposable Plates"
    ): "家居日用 / 一次性盘子",
    ("Household Essentials > Paper & Plastic > Food Storage Bags > Freezer Bags"): (
        "家居日用 / 冷冻保鲜袋"
    ),
    (
        "Industrial & Scientific > Food Service Equipment & Supplies > Sma"
        "llwares > Pot and Pan Lids"
    ): "工业商用 / 锅盖",
    (
        "Industrial & Scientific > Janitorial & Sanitation Supplies > Clea"
        "ning Tools > Commercial Disposable & Microfiber Cloths"
    ): "工业商用 / 商用一次性及超细纤维抹布",
    (
        "Industrial & Scientific > Janitorial & Sanitation Supplies > Clea"
        "ning Tools > Commercial Sponges & Scouring Pads"
    ): "工业商用 / 商用海绵与百洁布",
    "Industrial & Scientific > Medical & Dental > Medical Bags": "工业商用 / 医疗用品包",
    (
        "Industrial & Scientific > Occupational Health & Safety Products > Medical Safety"
    ): "工业商用 / 医疗安全防护",
    "Jewelry > Watches > Watch Boxes": "珠宝手表 / 手表收纳盒",
    (
        "Jewelry > Womens Jewelry & Watches > Womens Jewelry > Womens Rings > Womens Rings"
    ): "珠宝手表 / 女士戒指",
    ("Musical Instruments > Microphones > Microphone Stands and Booms"): (
        "乐器配件 / 麦克风支架与悬臂"
    ),
    "Office Supplies > Binders & Accessories > Binding Supplies": "办公用品 / 装订用品",
    "Office Supplies > Desk Organization > Bookends": "办公用品 / 书挡",
    ("Office Supplies > Desk Organization > Mail & Literature Organizers"): (
        "办公用品 / 信件与资料收纳架"
    ),
    "Office Supplies > Moving > All Moving Supplies": "搬家包装 / 全部搬家用品",
    "Office Supplies > Moving > Moving Boxes > Small Moving Boxes": "搬家包装 / 小号搬家纸箱",
    "Office Supplies > Moving > Packing Materials > Packing Tape": "搬家包装 / 封箱胶带",
    "Office Supplies > Moving > Packing Materials > Poly Bags": "搬家包装 / 塑料包装袋",
    "Office Supplies > Pencil Cases > Clear Pencil Boxes": "办公用品 / 透明文具盒",
    ("Office Supplies > Presentation Boards & Presentation Easels > Poster Boards"): (
        "办公用品 / 海报板"
    ),
    (
        "Office Supplies > Presentation Boards & Presentation Easels > White Poster Board"
    ): "办公用品 / 白色海报板",
    ("Office Supplies > Retail Essentials > Money Handling > Money Deposit Bags"): (
        "办公用品 / 现金存款袋"
    ),
    ("Office Supplies > Teaching and Classroom Supplies > Bulletin Board Borders"): (
        "办公用品 / 公告板装饰边框"
    ),
    (
        "Office Supplies > Teaching and Classroom Supplies > Teaching Aids > Pocket Charts"
    ): "办公用品 / 教学插袋挂图",
    (
        "Party & Occasions > Bachelorette Party Supplies > Bachelorette Pa"
        "rty Balloons & Decorations"
    ): "派对节庆 / 单身派对气球与装饰",
    (
        "Party & Occasions > Birthday Shop > Birthday Party Supplies > Birthday Party Favors"
    ): "派对节庆 / 生日派对回礼",
    ("Party & Occasions > Easter Party Supplies > Easter Hanging Decorations"): (
        "派对节庆 / 复活节悬挂装饰"
    ),
    ("Party & Occasions > Mermaid Party Supplies > Mermaid Party Decorations"): (
        "派对节庆 / 美人鱼主题派对装饰"
    ),
    (
        "Party & Occasions > Party Supplies > Baby Shower Party Supplies > Baby Shower Decorations"
    ): "派对节庆 / 迎婴派对装饰",
    (
        "Party & Occasions > Party Supplies > Party Decorations > Balloons"
        " > Balloon Accessories > All Balloon Accessories"
    ): "派对节庆 / 全部气球配件",
    ("Party & Occasions > Party Supplies > Party Decorations > Hanging Decorations"): (
        "派对节庆 / 悬挂装饰"
    ),
    (
        "Party & Occasions > Party Supplies > Party Decorations > Party Decoration Kits"
    ): "派对节庆 / 派对装饰套装",
    (
        "Party & Occasions > Party Supplies > St. Patrick's Day Party Supp"
        "lies > St. Patrick's Day Decorations > St. Patrick's Day Home Dec"
        "orations"
    ): "派对节庆 / 圣帕特里克节家居装饰",
    (
        "Party & Occasions > Thanksgiving Party Supplies > Thanksgiving Dessert & Treat Decorating"
    ): "派对节庆 / 感恩节甜点装饰用品",
    ("Party & Occasions > Wedding Shop > The Wedding Day > Reception Decor"): (
        "派对节庆 / 婚宴接待装饰"
    ),
    "Party & Occasions > Wedding Shop > Wedding Accessories": "派对节庆 / 婚礼配件",
    (
        "Party & Occasions > Wedding Shop > Wedding Party Supplies > Wedding Party Tableware"
    ): "派对节庆 / 婚礼派对餐具",
    ("Patio & Garden > Clearance Patio & Garden > Clearance Outdoor Cooking"): (
        "庭院园艺 / 户外烹饪清仓专区"
    ),
    "Patio & Garden > Garden Center > Composters > Shop All Composters": "庭院园艺 / 全部堆肥箱",
    "Patio & Garden > Garden Center > Garden Tools > Garden Accessories": "庭院园艺 / 园艺配件",
    ("Patio & Garden > Garden Center > Garden Tools > Shop All Garden Tools"): (
        "庭院园艺 / 全部园艺工具"
    ),
    "Patio & Garden > Garden Center > Hose Reels & Storage > Hose Holders": "庭院园艺 / 水管固定架",
    (
        "Patio & Garden > Garden Center > Hose Reels & Storage > Wall-Mounted Hose Reels"
    ): "庭院园艺 / 壁挂式水管卷盘",
    "Patio & Garden > Garden Center > Landscaping > Fencing > Chicken Wire": "庭院园艺 / 养鸡围网",
    "Patio & Garden > Garden Center > Lawn Care > Sprayers": "庭院园艺 / 喷洒器",
    "Patio & Garden > Garden Center > Outdoor Trash Cans": "庭院园艺 / 户外垃圾桶",
    ("Patio & Garden > Garden Center > Plant Care > Plant Supports > Garden Stakes"): (
        "庭院园艺 / 园艺固定桩"
    ),
    (
        "Patio & Garden > Garden Center > Pots & Planters > Indoor Planter"
        "s > Indoor Hanging Planters"
    ): "庭院园艺 / 室内吊挂花盆",
    (
        "Patio & Garden > Garden Center > Pots & Planters > Indoor Planters > Terrarium Planters"
    ): "庭院园艺 / 微景观植物盆",
    "Patio & Garden > Garden Center > Pots & Planters > Plant Caddies": "庭院园艺 / 花盆移动托盘",
    (
        "Patio & Garden > Outdoor Cooking > Grill Accessories > Griddle & "
        "Flat Top Accessories > Grill Mats"
    ): "庭院园艺 / 烧烤垫",
    (
        "Patio & Garden > Outdoor Cooking > Grill Accessories > Griddle & "
        "Flat Top Accessories > Outdoor Griddle Tools & Accessories"
    ): "庭院园艺 / 户外煎烤盘工具与配件",
    (
        "Patio & Garden > Outdoor Cooking > Grill Accessories > Grill Clea"
        "ning & Maintenance > Grill Cleaning Tools"
    ): "庭院园艺 / 烧烤炉清洁工具",
    (
        "Patio & Garden > Outdoor Cooking > Grill Accessories > Grill Cook"
        "ware and Supplies > Grill Grates & Racks"
    ): "庭院园艺 / 烧烤炉烤网与烤架",
    (
        "Patio & Garden > Outdoor Power Equipment > Outdoor Power Equipmen"
        "t Parts and Accessories > Pressure Washer Accessories > Pressure "
        "Washer Attachments"
    ): "庭院园艺 / 高压清洗机附件",
    (
        "Patio & Garden > Outdoor Power Equipment > Outdoor Power Equipmen"
        "t Parts and Accessories > Trimmers and Edgers Parts and Accessori"
        "es > String Trimmer Lines > .065 String Trimmer Lines"
    ): "庭院园艺 / 0.065英寸割草机尼龙线",
    (
        "Patio & Garden > Outdoor Shade > Outdoor Blinds & Shades > Shade Cloth & Accessories"
    ): "庭院园艺 / 遮阳网及配件",
    "Patio & Garden > Outdoor Shade > Outdoor Curtains": "庭院园艺 / 户外窗帘",
    ("Patio & Garden > Patio & Outdoor Decor > Flagpoles > Shop All Flagpoles"): (
        "庭院园艺 / 全部旗杆"
    ),
    (
        "Patio & Garden > Patio & Outdoor Decor > Garden Decorations > Pinwheels & Spinners"
    ): "庭院园艺 / 风车与旋转装饰",
    ("Patio & Garden > Patio & Outdoor Decor > Garden Statues > Goose Statues"): (
        "庭院园艺 / 鹅造型雕像"
    ),
    "Patio & Garden > Patio & Outdoor Decor > Porch Goose": "庭院园艺 / 门廊鹅装饰摆件",
    "Patio & Garden > Patio & Outdoor Decor > Wind Chimes": "庭院园艺 / 风铃",
    (
        "Patio & Garden > Patio Furniture > Patio Tables > Outdoor Side & Accent Tables"
    ): "庭院园艺 / 户外边几与装饰桌",
    ("Patio & Garden > Wild Bird Supplies > Bird Feeders > Platform Feeders"): (
        "庭院园艺 / 平台式喂鸟器"
    ),
    ("Patio & Garden > Wild Bird Supplies > Bird Houses > Bluebird Houses"): (
        "庭院园艺 / 蓝知更鸟鸟屋"
    ),
    "Personal Care > Bath & Body > Bath & Shower > Loofahs": "美妆个护 / 丝瓜络沐浴擦",
    "Personal Care > Incontinence > All Incontinence": "美妆个护 / 全部失禁护理用品",
    (
        "Personal Care > Regimens and Routines > Men's Shave Routine > Razors and Trimmers"
    ): "美妆个护 / 剃须刀与修剪器",
    "Pets > Birds > All Bird Supplies": "宠物用品 / 全部鸟类用品",
    (
        "Pets > Cats > Cat Feeders, Fountains, and Bowls > All Cat Feeders, Fountains, and Bowls"
    ): "宠物用品 / 全部猫咪喂食器、饮水器与食盆",
    (
        "Pets > Cats > Cat Litter and Accessories > Cat Litter Box Accessories > Cat Litter Scoops"
    ): "宠物用品 / 猫砂铲",
    "Pets > Cats > Cat Scratchers > All Cat Scratchers": "宠物用品 / 全部猫抓板",
    "Pets > Chickens > Chicken Feeders": "宠物用品 / 鸡用喂食器",
    "Pets > Chickens > Chicken Roost": "宠物用品 / 鸡栖架",
    ("Pets > Dogs > Dog Bowls and Accessories > All Dog Bowls and Accessories"): (
        "宠物用品 / 全部狗食盆及配件"
    ),
    ("Pets > Dogs > Dog Bowls and Accessories > Dog Food Storage Containers"): (
        "宠物用品 / 狗粮储存容器"
    ),
    "Pets > Dogs > Dog Carriers > All Dog Carriers": "宠物用品 / 全部狗狗外出箱包",
    "Pets > Dogs > Dog Carriers > Dog Car Seats": "宠物用品 / 狗狗车载座椅",
    (
        "Pets > Dogs > Dog Collars, Leashes, and Harnesses > All Dog Collars & Leashes"
    ): "宠物用品 / 全部狗项圈与牵引绳",
    "Pets > Dogs > Dog Crates > Dog Crate Mats": "宠物用品 / 狗笼垫",
    "Pets > Dogs > Dog Grooming > All Dog Grooming": "宠物用品 / 全部狗狗美容护理用品",
    "Pets > Dogs > Dog Health and Wellness > Dog Cones": "宠物用品 / 狗狗防舔伊丽莎白圈",
    ("Pets > Dogs > Dog Potty Training > All Dog Potty Training"): (
        "宠物用品 / 全部狗狗定点如厕训练用品"
    ),
    "Pets > Dogs > Dog Potty Training > Puppy Pads > All Puppy Pads": "宠物用品 / 全部幼犬尿垫",
    "Pets > Fish Supplies > All Fish Tanks and Supplies": "宠物用品 / 全部鱼缸及用品",
    "Pets > Fish Supplies > Fish Aquarium Cleaners": "宠物用品 / 鱼缸清洁工具",
    "Pets > Reptiles > Turtles > All Turtles": "宠物用品 / 全部宠物龟用品",
    "Pets > Small Pets > All Small Pets": "宠物用品 / 全部小型宠物用品",
    (
        "Sports & Outdoors > Exercise & Fitness > Exercise & Fitness Acces"
        "sories > All Exercise and Fitness Accessories"
    ): "运动户外 / 全部运动健身配件",
    (
        "Sports & Outdoors > Exercise & Fitness > Exercise & Fitness Acces"
        "sories > Balance Boards > Surf Balance Boards"
    ): "运动户外 / 冲浪平衡训练板",
    (
        "Sports & Outdoors > Exercise & Fitness > Exercise & Fitness Acces"
        "sories > Jump Ropes > All Jump Ropes"
    ): "运动户外 / 全部跳绳",
    (
        "Sports & Outdoors > Exercise & Fitness > Sports Recovery, Injury "
        "Prevention > Foam Rollers > Muscle Roller Stick"
    ): "运动户外 / 肌肉按摩滚轮棒",
    (
        "Sports & Outdoors > Exercise & Fitness > Strength Training > Weig"
        "ht Lifting Accessories > Landmine Attachments > All Landmine Atta"
        "chments"
    ): "运动户外 / 全部杠铃地雷管配件",
    (
        "Sports & Outdoors > Exercise & Fitness > Strength Training > Weig"
        "ht Lifting Accessories > Weight Training Accessories"
    ): "运动户外 / 力量训练配件",
    (
        "Sports & Outdoors > Exercise & Fitness > Strength Training > Weig"
        "hts > Weight Lifting Equipment"
    ): "运动户外 / 举重装备",
    (
        "Sports & Outdoors > Exercise & Fitness > Strength Training > Weig"
        "hts > Weight Storage > Dumbbell Rack"
    ): "运动户外 / 哑铃架",
    ("Sports & Outdoors > Exercise & Fitness > Yoga > Gym Mats > All Gym Mats"): (
        "运动户外 / 全部健身垫"
    ),
    "Sports & Outdoors > Exercise & Fitness > Yoga > Yoga Mats": "运动户外 / 瑜伽垫",
    "Sports & Outdoors > Outdoor Sports > Boating > Boat Accessories": "运动户外 / 船艇配件",
    (
        "Sports & Outdoors > Outdoor Sports > Camping Gear > Camping Acces"
        "sories > All Camping Accessories"
    ): "运动户外 / 全部露营配件",
    (
        "Sports & Outdoors > Outdoor Sports > Camping Gear > Camping Emergency Preparedness"
    ): "运动户外 / 露营应急装备",
    (
        "Sports & Outdoors > Outdoor Sports > Camping Gear > Tents > Tent "
        "Accessories > Tent Guylines"
    ): "运动户外 / 帐篷防风绳",
    (
        "Sports & Outdoors > Outdoor Sports > Fishing > Family Fishing Spe"
        "cialty Shops > Saltwater Fishing"
    ): "运动户外 / 海水钓鱼",
    (
        "Sports & Outdoors > Outdoor Sports > Fishing > Fishing Lures & Baits > Fish Attractants"
    ): "运动户外 / 诱鱼剂",
    (
        "Sports & Outdoors > Recreation > Game Room > Pool & Billiards > C"
        "ue Stick Accessories > All Cue Stick Accessories"
    ): "运动户外 / 全部台球杆配件",
    "Sports & Outdoors > Sports > Coaching Supplies": "运动户外 / 运动训练教练用品",
    ("Sports & Outdoors > Sports > Golf Equipment > Driver Headcovers"): (
        "运动户外 / 高尔夫木杆杆头套"
    ),
    (
        "Sports & Outdoors > Sports > Golf Equipment > Golf Balls > Golf B"
        "alls By Type > Practice Golf Balls"
    ): "运动户外 / 高尔夫练习球",
    ("Sports & Outdoors > Sports > Golf Equipment > Golf Swing Trainers"): (
        "运动户外 / 高尔夫挥杆训练器"
    ),
    (
        "Subscriptions > Subscription Household Essential > browse subscri"
        "ption food prep and storage"
    ): "订阅商品 / 订阅商品：食品准备与收纳",
    "Toys > All Toys & Games": "玩具用品 / 全部玩具与游戏",
    "Toys > Bikes > Bike Accessories > Bike Water Bottle Cages": "玩具用品 / 自行车水壶架",
    "Toys > Games & Puzzles > Mahjong Accessories": "玩具用品 / 麻将配件",
    ("Toys > Games & Puzzles > Puzzles > Puzzle Accessories > Puzzle Accessories"): (
        "玩具用品 / 拼图配件"
    ),
}


_V5_SEGMENT_TRANSLATIONS = """
Accessories=配饰
Action Figures=可动人偶
Action Figures and Playsets=可动人偶与玩具套装
Air Conditioner Parts & Accessories=空调零件与配件
Air Purifier Filters=空气净化器滤芯
Air Quality=空气质量
Appliances Parts & Accessories=家电零件与配件
Artificial Plants and Flowers=仿真植物与花卉
Arts & Crafts Furniture and Storage=手工艺家具与收纳
Arts & Crafts for Kids=儿童手工艺用品
Audio=音频设备
Automotive Replacement Parts=汽车替换零件
Automotive Tools & Equipment=汽车工具与设备
Bags & Accessories=箱包与配饰
Bar & Wine Accessories=酒吧与葡萄酒配件
Barware=酒具
Basic Craft Supplies=基础手工材料
Bathroom Rugs & Bath Mats=浴室地毯与浴垫
Beading & Jewelry Making=串珠与首饰制作
Beading Supplies=串珠材料
Bike Accessories=自行车配件
Bikes=自行车
Bird Feeders=喂鸟器
Birthday Party Supplies=生日派对用品
Birthday Shop=生日主题专区
Brackets and Angle Irons=支架与角铁
Building Materials=建筑材料
Bungee Cords=弹力绑绳
Bungee Cords and Ratchet Straps=弹力绳与棘轮绑带
Cable Management=线缆整理
Candles & Home Fragrance=蜡烛与家居香氛
Car & Truck Racks, Cargo Carriers & Ratchet Straps=汽车行李架、货物载具与绑带
Car Anti-Theft Devices=汽车防盗装置
Car Organizers=汽车收纳用品
Car Safety & Car Security=汽车安全与防盗
Carnival Party Supplies=嘉年华派对用品
Cat Beds=猫窝
Cats=猫用品
Christmas Decor=圣诞装饰
Christmas Trees & Christmas Decor=圣诞树与圣诞装饰
Christmas Wreaths=圣诞花环
Cleaning Tools=清洁工具
Clear Bags=透明包袋
Clearance Patio & Garden=庭院园艺清仓专区
Closet Organizers=衣柜收纳用品
Coffee Shop=咖啡用品
Computer Keyboards & Mice=电脑键盘与鼠标
Computer Mouse & Mouse Pads=电脑鼠标与鼠标垫
Computers, Laptops and Tablets=电脑、笔记本与平板
Cooling=制冷设备
Craft Storage=手工材料收纳
Craft Supplies=手工材料
Crafting=手工制作
Cue Sticks=台球杆
Curtain Hanging Accessories=窗帘悬挂配件
Curtain Rods=窗帘杆
Curtains & Window Treatments=窗帘与窗饰
Decorative Accents=装饰摆件
Desk Organization=桌面收纳
Dishwasher Parts=洗碗机零件
Dog Bowls and Accessories=狗食盆与配件
Dog Collars, Leashes, and Harnesses=狗项圈、牵引绳与胸背带
Dog Toys=狗玩具
Dogs=狗用品
Door Hardware=门用五金
Doors and Gates=门与围栏
Dusters=除尘掸
Electrical=电工用品
Emergency Prep=应急准备
Extension Cord Reels=延长线卷线器
Exterior Car Parts & Accessories=汽车外部零件与配件
Fish Supplies=鱼类用品
Fish Tank Decoration=鱼缸装饰
Food Holding and Warming Equipment=食品保温与加热设备
Food Service Equipment & Supplies=餐饮服务设备与用品
Food Storage Bags=食品保鲜袋
Furniture Hardware=家具五金
Game Room=游戏室
Games & Puzzles=游戏与益智玩具
Garage Door Hardware=车库门五金
Garage Door Openers and Hardware=车库门开门器与五金
Green Party Supplies=绿色主题派对用品
HVAC Ducting and Ventilation=暖通风管与通风设备
Hand Tools=手动工具
Health & Safety=健康与安全
Health and Medicine=健康与医疗
Heating, Cooling, & Air Quality=供暖、制冷与空气质量
Hinges=铰链
Holiday Decor=节日装饰
Hooks=挂钩
Instrument Accessories=乐器配件
Insulation=保温隔热材料
Interior Parts & Accessories=汽车内饰零件与配件
Janitorial & Sanitation Supplies=清洁保洁与卫生用品
Janitorial Disposables=一次性保洁用品
Kitchen Appliance Parts & Accessories=厨房电器零件与配件
Kitchen Sinks Plumbing=厨房水槽管道
Kitchen Storage & Organization=厨房收纳与整理
Labels=标签
Labels & Label Makers=标签与标签机
Laundry Storage & Organization=洗衣收纳与整理
Makeup=化妆用品
Massage=按摩
Metallic Party Supplies=金属色主题派对用品
Mixers & Attachments=搅拌机与配件
Mops=拖把
Odor Maintainers=除味用品
Outdoor Planters=户外花盆
Outdoor Power Equipment=户外动力设备
Outdoor Power Equipment Parts and Accessories=户外动力设备零件与配件
Party Supplies by Color=按颜色分类的派对用品
Patio Furniture Covers=庭院家具罩
Picture Hangers=挂画配件
Pool & Billiards=台球与桌球
Pots & Planters=花盆与种植容器
Pressure Washer Accessories=高压清洗机配件
Pricemaking Supplies=标价用品
Recliners=躺椅
Recover From Surgery=术后康复
Recreation=休闲活动
Refrigerator & Freezer Parts=冰箱与冷冻柜零件
Retail Essentials=零售必备用品
Return to Function After Injury=伤后功能康复
Rug Pads=地毯垫
Rugs=地毯
School Supplies=学习用品
Serveware=餐桌盛放器具
Sheds & Outdoor Storage=户外棚屋与收纳
Shop Fabric by Size=按尺寸选购布料
Shop Plumbing by Fixture=按卫浴设备选购管道配件
Shop Tie Downs And Straps by Vehicle=按车型选购捆绑带
Shower and Bathtub Plumbing=淋浴与浴缸管道
Sponges and Scrubbers=海绵与擦洗工具
Sports Medicine & Injury Recovery Solution=运动医疗与损伤康复
Steering Wheel Covers=方向盘套
Steering Wheel Covers by Color=按颜色分类的方向盘套
Storage Baskets & Bins=收纳篮与收纳箱
Store Fixtures & Equipment=商店陈列设备
String Instrument Accessories=弦乐器配件
Tennis & Racquets=网球与球拍运动
The Wedding Day=婚礼当天用品
Tie Downs And Straps=捆绑带
Tie Downs, Anchors & Bungees=绑带、锚固件与弹力绳
Tire Inflators=轮胎充气泵
Tire and Wheel Accessories=轮胎与车轮配件
Tires & Accessories=轮胎与配件
Toilet Installation & Repair Tools=马桶安装与维修工具
Toilet Plumbing=马桶管道
Tool Equipment & Storage=工具设备与收纳
Tools & Gadgets=工具与小配件
Towing Hitches, Winches & Accessories=拖车挂钩、绞盘与配件
Trash Cans=垃圾桶
Travel Accessories=旅行配件
Treadmill Accessories=跑步机配件
Treadmills=跑步机
Vacuums, Steamers & Floor Care=吸尘、蒸汽与地面清洁设备
Wall Art=墙面艺术装饰
Walmart for Business=沃尔玛企业采购
Washer & Dryer Parts=洗衣机与烘干机零件
Watering & Irrigation=浇水与灌溉
Weatherproofing=防风雨防护
Wedding Shop=婚礼用品专区
Wild Bird Supplies=野鸟用品
Window Weatherproofing=窗户防风雨密封
Windows & Window Supplies=窗户与窗户配件
Yoga=瑜伽
Zip Tie Sizes=扎带尺寸
Zip Ties=扎带
.065 String Trimmer Lines=0.065英寸割草机尼龙线
12 Inch Zip Ties=12英寸扎带
3 Drawer Nightstand=三抽屉床头柜
6 Inch Polishing Pads=6英寸抛光垫
8 Inch Zip Ties=8英寸扎带
Action Figure Core=基础款可动人偶
Air Compressor Accessories=空气压缩机配件
Air Compressors=空气压缩机
Air Tools=气动工具
All Air Conditioner Parts & Accessories=全部空调零件与配件
All Air Purifier Filters=全部空气净化器滤芯
All Artificial Plants and Flowers=全部仿真植物与花卉
All Balloon Accessories=全部气球配件
All Bird Supplies=全部鸟类用品
All Brackets and Angle Irons=全部支架与角铁
All Camping Accessories=全部露营配件
All Cat Beds=全部猫窝
All Cat Feeders, Fountains, and Bowls=全部猫咪喂食器、饮水器与食盆
All Cat Scratchers=全部猫抓板
All Cue Stick Accessories=全部台球杆配件
All Cutting Boards=全部砧板
All Dog Bowls and Accessories=全部狗食盆及配件
All Dog Carriers=全部狗狗外出箱包
All Dog Collars & Leashes=全部狗项圈与牵引绳
All Dog Grooming=全部狗狗美容护理用品
All Dog Potty Training=全部狗狗定点如厕训练用品
All Dog Toys=全部狗玩具
All Door Hardware=全部门用五金
All Drill Bits=全部钻头
All Dusters=全部除尘掸
All Electronics Carrying Cases=全部电子设备收纳包
All Exercise and Fitness Accessories=全部运动健身配件
All Fish Tanks and Supplies=全部鱼缸及用品
All Floral Arranging Supplies=全部插花用品
All Frosting, Toppings, & Decorations=全部糖霜、配料与烘焙装饰
All Garage Door Hardware=全部车库门五金
All Gym Mats=全部健身垫
All Incontinence=全部失禁护理用品
All Jump Ropes=全部跳绳
All Labels & Stickers=全部标签与贴纸
All Landmine Attachments=全部杠铃地雷管配件
All Mops=全部拖把
All Moving Supplies=全部搬家用品
All Nursery Storage=全部婴儿房收纳用品
All Pool and Billiard Sticks=全部台球杆
All Puppy Pads=全部幼犬尿垫
All RV Levelers=全部房车调平器
All RV Water Filters=全部房车净水滤芯
All Recliners=全部躺椅
All Rug Pads & Grippers=全部地毯垫与防滑固定用品
All Small Pets=全部小型宠物用品
All Step Stools=全部踏脚凳
All Toys & Games=全部玩具与游戏
All Treadmill Accessories=全部跑步机配件
All Turtles=全部宠物龟用品
All Walmart Restored Cooling and Heating=全部沃尔玛翻新制冷与供暖设备
All Walmart Restored Small Appliances=全部沃尔玛翻新小家电
Appliance Belts=家电传动皮带
Appliance Handles=家电把手
Aquarium Plants=鱼缸造景水草
Art & Craft Kits=美术与手工套装
Art Painting Supplies=绘画用品
Art Supplies=美术用品
Art and Poster Tubes=画作与海报收纳筒
Artificial Flowers=仿真花
Artist Easels=绘画画架
Attic Insulation=阁楼隔热材料
Audio Visual Accessories=音视频配件
Auto Body=汽车车身
Auto Paint Tools=汽车喷漆工具
Auto Sandpaper and Abrasives=汽车打磨砂纸与磨料
Auto Tool Storage=汽车工具收纳
Automotive Electrical=汽车电气
Automotive Paint=汽车喷漆用品
Automotive Stands and Supports=汽车维修支架与支撑工具
Avocado Slicers=牛油果切片器
Baby Decor=婴儿房装饰
Baby Proofing=婴幼儿安全防护
Baby Shower Decorations=迎婴派对装饰
Baby Shower Party Supplies=迎婴派对用品
Baby Wipe Dispenser=婴儿湿巾盒
Bachelorette Party Balloons & Decorations=单身派对气球与装饰
Bachelorette Party Supplies=婚前单身派对用品
Back Seat Organizers=汽车后座收纳袋
Bag & Chip Clips=包装袋与零食封口夹
Bakeware Sets=烘焙器具套装
Baking & Cookie Sheets=烘焙烤盘与饼干烤盘
Baking & Pastry Tools=烘焙与糕点工具
Baking Decorations=烘焙装饰用品
Baking Dishes=烘焙烤皿
Baking Ingredients=烘焙原料
Balance Boards=平衡板
Balloon Accessories=气球配件
Balloons=气球
Bar Tools=调酒工具
Baskets=篮筐
Bath & Body=沐浴与身体护理
Bath & Shower=浴室与淋浴用品
Bath Towel Sets=浴巾套装
Bath Towels=浴巾
Bathing After Surgery=术后洗浴辅助用品
Bathroom Cabinets & Fixtures=浴室柜与固定设施
Bathroom Cleaning Supplies=浴室清洁用品
Bathroom Hardware=浴室五金
Bathroom Plumbing=浴室管道与卫浴配件
Bathroom Renovation=浴室装修
Bathroom Sets=浴室用品套装
Bathroom Sink Drains=浴室洗手盆排水配件
Bathroom Sink Plumbing=浴室洗手盆管道
Bathroom Soap Dispenser Set=浴室皂液器套装
Bathroom Storage=浴室收纳
Bathtub Mats=浴缸防滑垫
Bathtub Stoppers=浴缸排水塞
Batter Dispensers=面糊分配器
Beading Storage=串珠材料收纳
Beads=串珠
Beer & Wine Glasses=啤酒杯与葡萄酒杯
Bidet & Washlet Accessories=坐浴盆与智能马桶盖配件
Bidet Sprayers=冲洗喷枪
Bike Bags & Carriers=自行车包与载物架
Bike Baskets=自行车车篮
Bike Water Bottle Cages=自行车水壶架
Binders & Accessories=活页夹及配件
Binding Supplies=装订用品
Bird Houses=鸟屋
Birds=鸟类用品
Birthday Hanging Decorations=生日派对悬挂装饰
Birthday Party Decorations=生日派对装饰
Birthday Party Favors=生日派对回礼
Black Steering Wheel Covers=黑色方向盘套
Blank Media=空白存储介质
Blinds=百叶帘
Blinds & Shades=百叶帘与遮阳帘
Bluebird Houses=蓝知更鸟鸟屋
Boat Accessories=船艇配件
Boating=船艇运动
Bobbins=缝纫机梭芯
Bolts=螺栓
Bookends=书挡
Bottle Feeding=奶瓶喂养
Bowls=碗
Brooms=扫帚
Bulletin Board Borders=公告板装饰边框
Bungee Cords with Hooks=带钩弹力绑绳
Burger Press=汉堡肉饼压模
Cabinet Hinges=橱柜铰链
Cable Concealer=线缆隐藏槽
Cake & Bundt Pans=蛋糕烤模与环形蛋糕模
Cake Stands=蛋糕架
Camping Accessories=露营配件
Camping Emergency Preparedness=露营应急装备
Camping Gear=露营装备
Can Openers=开罐器
Candle Holders=烛台
Car Console Organizers=汽车中控台收纳用品
Car Detailing=汽车精细美容
Car Polishing Pads=汽车抛光垫
Car Seat Covers=汽车座椅套
Car Seat Covers by Feature=按功能分类的汽车座椅套
Car Straps=车辆捆绑带
Car Trash Cans=车载垃圾桶
Car Wash Brush with Handle=带手柄洗车刷
Car Wash Brushes=洗车刷
Car Wash Mitts=洗车手套
Car Wash Sponges=洗车海绵
Car Wash Supplies=洗车用品
Carnival Party Decorations=嘉年华派对装饰
Carry On Luggage=随身登机箱
Cat Feeders, Fountains, and Bowls=猫咪喂食器、饮水器与食盆
Cat Litter Box Accessories=猫砂盆配件
Cat Litter Scoops=猫砂铲
Cat Litter and Accessories=猫砂与配件
Cat Scratchers=猫抓板
Ceremony Essentials=婚礼仪式用品
Chair Sashes=椅背装饰带
Chalk Lines and Reels=墨斗线与卷线器
Cheese Slicers=奶酪切片器
Chicken Feeders=鸡用喂食器
Chicken Roost=鸡栖架
Chicken Wire=养鸡围网
Chickens=养鸡用品
Chopping & Slicing=切碎与切片工具
Christmas Trim a Home=圣诞家居装饰
Circular Saw Blades=圆锯片
Classic Games=经典游戏
Cleaning Brushes=清洁刷
Cleaning Refills=清洁工具替换件
Clear Makeup Bags=透明化妆包
Clear Pencil Boxes=透明文具盒
Clear Storage Bins=透明收纳箱
Clearance Outdoor Cooking=户外烹饪清仓专区
Clearance Outdoor Lighting=户外照明清仓专区
Clothes Hanging Rods for Cars=车用挂衣杆
Clothes Protectors=衣物防护罩
Coaching Supplies=运动训练教练用品
Coasters=杯垫
Coat Hooks=衣帽挂钩
Coat Racks=衣帽架
Coffee & Espresso Parts and Accessories=咖啡机与意式咖啡机配件
Coffee Decanters & Carafes=咖啡壶与玻璃分享壶
Coffee Mugs=咖啡杯
Coffee Tables=茶几
Collectibles=收藏品
Commercial Air Fresheners & Deodorizers=商用空气清新及除臭用品
Commercial Disposable & Microfiber Cloths=商用一次性及超细纤维抹布
Commercial Sponges & Scouring Pads=商用海绵与百洁布
Commercial Toilet Paper Dispensers & Holders=商用卫生纸分配器与支架
Composters=堆肥箱
Condiment Servers=调味品盛放器
Corner Shower Shelves=淋浴房转角置物架
Cosmetic Cottons=化妆棉
Cotton Swabs=棉签
Counter Organizers=厨房台面收纳用品
Craft & Hobby Storage Bags & Cases=手工材料收纳包及收纳盒
Craft Shells=手工贝壳材料
Craft Vinyl=手工刻字贴膜
Crib Mobiles=婴儿床旋转挂饰
Cue Stick Accessories=台球杆配件
Curtain Hardware=窗帘五金配件
Curtain Tie Backs=窗帘绑带
Cutting Boards=砧板
Cutting Mats=切割垫
Daily Living Aids=日常生活辅助用品
Decorative Balls=装饰球
Decorative Bowls=装饰碗
Decorative Boxes=装饰盒
Decorative Pillows & Throws=装饰抱枕与盖毯
Decorative Pillows & Throws Shop All=全部装饰抱枕与盖毯
Decorative Stones=装饰石
Decorative Trays=装饰托盘
Deep Fryers=油炸锅
Diaper Caddy=尿布收纳篮
Diaper Organizers=尿布收纳用品
Diapering=换尿布用品
Die Cutting=模切用品
Dimmers, Switches, and Wall Plates=调光器、开关与墙壁面板
Dinnerware & Serving Storage=餐具与上菜器皿收纳
Dirt Bike Hand Controls=越野摩托车手柄控制件
Dirt Bike Handlebar Crossbars=越野摩托车车把横杆
Dirt Bike Parts=越野摩托车零件
Dirt Bike Parts & Accessories=越野摩托车零件与配件
Dish Brushes=洗碗刷
Dishwasher Accessories=洗碗机配件
Dishwasher Baskets & Racks=洗碗机篮筐与碗架
Display Cases=展示柜
Disposable Bowls=一次性碗
Disposable Plates=一次性盘子
Dog Bowls and Feeders=狗食盆与喂食器
Dog Car Seats=狗狗车载座椅
Dog Carriers=狗狗外出箱包
Dog Cones=狗狗防舔伊丽莎白圈
Dog Crate Mats=狗笼垫
Dog Crates=狗笼
Dog Food Storage Containers=狗粮储存容器
Dog Grooming=狗狗美容护理
Dog Health and Wellness=狗狗健康护理
Dog Potty Training=狗狗定点如厕训练
Dollies & Hand Trucks=搬运小车与手推车
Door Blinds=门用百叶帘
Door Closers=闭门器
Door Hinges=门铰链
Door Locks and Deadbolts=门锁与锁舌
Door Stops=门挡
Door Weatherproofing=门用防风雨密封
Door Weatherstripping=门缝密封条
Drains=排水配件
Drapery & Curtain Hooks=窗帘挂钩
Drill Bits=钻头
Drinking Glasses=饮用玻璃杯
Drinkware Accessories=饮具配件
Driver Headcovers=高尔夫木杆杆头套
Dryer Lint Screens=烘干机绒毛过滤网
Dryer Sheets=烘干机柔顺纸
Drying Racks=晾晒架
Duffel Bags=旅行圆筒包
Dumbbell Rack=哑铃架
EV Chargers=电动汽车充电器
EV Chargers by Type=按类型分类的电动汽车充电器
EV Parts & Accessories=电动汽车零件与配件
Easter Hanging Decorations=复活节悬挂装饰
Easter Party Supplies=复活节派对用品
Egg Slicers=鸡蛋切片器
Electric Vehicle Supply Equipment (EVSE)=电动汽车供电设备
Electronics Value Bundles=电子产品优惠组合套装
Embroidery=刺绣
Embroidery Floss & Thread=刺绣线
End Tables=边几
Entry Door Hardware=入户门五金
Exercise & Fitness Accessories=运动健身配件
Extension Cord Holders=延长线收纳架
Fabric by the Yard=按码销售布料
Fall Decor=秋季装饰
Fall Indoor Decor=秋季室内装饰
Family Fishing Specialty Shops=家庭钓鱼特色专区
Fasteners=紧固件
Feeding=喂养用品
Fencing=围栏
Fiberglass Insulation=玻璃纤维保温棉
File Organizers=文件整理架
Fills, Foam and Pillow Forms=填充材料、泡棉与抱枕芯
Fish Aquarium Cleaners=鱼缸清洁工具
Fish Attractants=诱鱼剂
Fishing Lures & Baits=钓鱼拟饵与鱼饵
Fitted Mattress Protectors=床垫保护套
Flagpoles=旗杆
Flatware=刀叉勺餐具
Flatware Serving Utensils=分餐用刀叉勺
Floating Shelves=悬浮置物架
Flooring=地面铺装材料
Flooring Shims & Spacers=地板安装垫片与间隔件
Floral Arranging=插花用品
Floss Organizer Sets=绣线收纳套装
Foam Rollers=泡沫按摩轴
Food Bags=食品保鲜袋
Food Choppers=食物切碎器
Food Peelers=削皮器
Food Prep=食材预处理工具
Food Thermometers=食物温度计
Foot Care=足部护理
Framed Wall Art=装框墙面装饰画
Freezer Bags=冷冻保鲜袋
Fridge Magnets=冰箱贴
Frosting, Toppings & Decorations=糖霜、配料与烘焙装饰
Fruit & Vegetable Tools=水果与蔬菜工具
Fryers=炸锅
Frying Pans & Skillets=煎锅和平底锅
Furniture Legs=家具腿
Furniture Pads=家具防护垫
Garage Roller Seats And Creepers=车库维修滑轮凳与躺板
Garage Storage=车库收纳
Garage and Shop=车库与维修车间用品
Garden Accessories=园艺配件
Garden Decorations=园艺装饰
Garden Planters=园艺种植盆
Garden Stakes=园艺固定桩
Garden Statues=花园雕像
Garden Tools=园艺工具
Garment Bags=衣物防尘袋
General Electronic Accessories=通用电子产品配件
Glass Candle Holders=玻璃烛台
Glass Storage Containers=玻璃收纳容器
Golf Balls=高尔夫球
Golf Balls By Type=按类型分类的高尔夫球
Golf Equipment=高尔夫装备
Golf Swing Trainers=高尔夫挥杆训练器
Goose Statues=鹅造型雕像
Graters=刨丝器
Green Party Decorations=绿色主题派对装饰
Griddle & Flat Top Accessories=煎烤盘与平板烤炉配件
Griddles & Grill Pans=平底煎盘与烤盘
Grill Accessories=烧烤炉配件
Grill Cleaning & Maintenance=烧烤炉清洁与维护
Grill Cleaning Tools=烧烤炉清洁工具
Grill Cookware and Supplies=烧烤炊具与用品
Grill Grates & Racks=烧烤炉烤网与烤架
Grill Mats=烧烤垫
Ground Feeders=地面喂鸟器
Gym Mats=健身垫
Hair Accessories=发饰
Hair Tools & Accessories Combined=美发工具及配件
Halloween Decor=万圣节装饰
Halloween Tabletop Decor=万圣节餐桌装饰
Hammers=锤子
Hand Towel Holders=擦手巾架
Hand Towels=擦手巾
Hand Trucks=手推搬运车
Handbags=手提包
Hangers=衣架
Hanging Closet Organizers=悬挂式衣柜收纳架
Hanging Decorations=悬挂装饰
Hanging Planters=吊挂花盆
Hardware Tape=五金胶带
Heavy Duty Zip Ties=重型扎带
Home Health Care=居家健康护理
Hose Holders=水管固定架
Hose Nozzles=水管喷头
Hose Reels & Storage=水管卷盘与收纳
House Hooks=家用挂钩
Hunting Food Storage=狩猎食品储存用品
Incontinence=失禁护理用品
Indoor Halloween Decor=万圣节室内装饰
Indoor Hanging Planters=室内吊挂花盆
Indoor Planters=室内花盆
Insoles=鞋垫
Interior Repair & Restoration=汽车内饰维修与修复
Jack Accessories=千斤顶配件
Jack Pads=千斤顶支撑垫
Jigsaws=曲线锯
Jump Ropes=跳绳
Junk Journal Supplies=拼贴手账材料
Keychains=钥匙扣
Kid Art Easels & Stations=儿童画架与绘画台
Kids' Furniture=儿童家具
Kids' Room Decor=儿童房装饰
Kids' Rooms=儿童房
Kids' Wall Decals & Stickers=儿童墙贴与装饰贴纸
Kids' Water Bottles=儿童水壶
Kitchen & Dining Furniture=厨房与餐厅家具
Kitchen & Table Linens=厨房与餐桌布艺
Kitchen Canisters=厨房储物罐
Kitchen Drawer Organizers=厨房抽屉收纳用品
Kitchen Islands & Carts=厨房中岛与推车
Kitchen Sink Drains=厨房水槽排水配件
Kitchen Spatulas=厨房铲勺
Knick-Knacks=家居小摆件
Koozies=饮料保冷杯套
Ladders and Step Stools=梯子与踏脚凳
Landmine Attachments=杠铃地雷管训练配件
Landscaping=园林景观用品
Laundry Bags=洗衣袋
Laundry Hampers=脏衣篮
Lawn Care=草坪养护
Lemon Squeezer=柠檬榨汁器
Loofahs=丝瓜络沐浴擦
Lug Nuts & Lug Nut Sets=车轮螺母与套装
Lug Nuts, Lug Nut Covers & Lug Nut Keys=车轮螺母、螺母盖与拆卸钥匙
Luggage Racks=行李架
Macrame Wall Hangings=绳编墙饰
Mahjong Accessories=麻将配件
Mail & Literature Organizers=信件与资料收纳架
Makeup Tools & Brushes=化妆工具与化妆刷
Makeup Tools and Accessories=化妆工具及配件
Mallets=木槌与橡胶锤
Mason Jars=梅森玻璃罐
Mattress Covers & Protectors=床垫罩与保护套
Measuring Cups=量杯
Meat Tools=肉类处理工具
Mechanics Tools=机械维修工具
Medical & Dental=医疗与牙科
Medical Bags=医疗用品包
Medical Safety=医疗安全防护
Medical Supplies & Equipment=医疗用品与设备
Medicine Cabinets=医药柜
Melamine Sponges=纳米清洁海绵
Men's Shave Routine=男士剃须护理
Mermaid Party Decorations=美人鱼主题派对装饰
Mermaid Party Supplies=美人鱼主题派对用品
Metal Wall Art=金属墙饰
Metallic Party Decorations=金属色主题派对装饰
Microfiber Wash Mitts=超细纤维洗车手套
Microphone Stands and Booms=麦克风支架与悬臂
Microphones=麦克风
Microwave Parts=微波炉零件
Money Deposit Bags=现金存款袋
Money Handling=现金处理用品
Moscow Mule Mugs=莫斯科骡子鸡尾酒杯
Mouse Pads & Wrist Rests=鼠标垫与腕托
Moving=搬家用品
Moving Boxes=搬家纸箱
Mud Flaps=汽车挡泥板
Mud Flaps & Splash Guards=挡泥板与防溅板
Muscle Roller Stick=肌肉按摩滚轮棒
Needle Arts=针线手工艺
Nightstands=床头柜
No Pull Dog Harnesses=防暴冲狗胸背带
Notions & Sewing Accessories=缝纫辅料及配件
Nursery & Decor=婴儿房与装饰
Nursery Storage and Organizers=婴儿房收纳用品
Occupational Health & Safety Products=职业健康与安全防护用品
Outdoor Blinds & Shades=户外百叶帘与遮阳帘
Outdoor Christmas Wreaths=户外圣诞花环
Outdoor Cooking=户外烹饪
Outdoor Curtains=户外窗帘
Outdoor Griddle Tools & Accessories=户外煎烤盘工具与配件
Outdoor Shade=户外遮阳用品
Outdoor Side & Accent Tables=户外边几与装饰桌
Outdoor Sports=户外运动
Outdoor Trash Cans=户外垃圾桶
Outlet Wall Plates=插座面板
Packing Cubes=行李收纳袋
Packing Materials=包装材料
Packing Tape=封箱胶带
Paint=油漆与涂料
Paint Supplies & Tools=油漆工具与用品
Pantry Organization=食品储藏室收纳
Paper Crafting=纸艺手工
Party Decoration Kits=派对装饰套装
Party Decorations=派对装饰
Pasta Tools=意面制作工具
Patio & Outdoor Decor=庭院与户外装饰
Patio Furniture=庭院家具
Patio Tables=庭院桌
Pegboard Hooks=洞洞板挂钩
Pencil Cases=笔袋与文具盒
Personal Protective Equipment=个人防护装备
Phone Car Mounts=车载手机支架
Picture Hanging Wire=挂画钢丝
Pinwheels & Spinners=风车与旋转装饰
Pitchers & Carafes=冷水壶与玻璃分享壶
Pizza Stones & Pans=披萨烤石与烤盘
Placemats=餐垫
Plant Caddies=花盆移动托盘
Plant Care=植物养护
Plant Stands=花架
Plant Supports=植物支撑架
Plastic Storage Bins & Boxes=塑料收纳箱与盒
Plate Hangers=盘子悬挂架
Platform Feeders=平台式喂鸟器
Plumbing Parts and Repairs=管道配件与维修
Pocket Charts=教学插袋挂图
Poly Bags=塑料包装袋
Porch Goose=门廊鹅装饰摆件
Poster Boards=海报板
Pot Racks & Organizers=锅具置物架与整理架
Pot and Pan Lids=锅盖
Potato Mashers & Ricers=土豆捣泥器与压泥器
Potties=儿童便盆
Potty Training=如厕训练用品
Power Saw Accessories=电锯配件
Power Saws=电锯
Power Tool Accessories=电动工具配件
Powersport Parts & Accessories=动力运动车辆零件与配件
Practice Golf Balls=高尔夫练习球
Presentation Boards & Presentation Easels=展示板与展示画架
Pressure Washer Attachments=高压清洗机附件
Pressure Washer Fittings=高压清洗机接头
Price Guns=标价枪
Puppy Pads=幼犬尿垫
Puzzle Accessories=拼图配件
Puzzles=拼图
RV Levelers=房车调平器
RV Parts & Accessories=房车零件与配件
RV Waste Water and Sanitation=房车废水处理与卫生用品
RV Water Filters=房车净水滤芯
Ratchet & Socket Combination Sets=棘轮扳手与套筒组合套装
Ratchets & Sockets=棘轮扳手与套筒
Razors and Trimmers=剃须刀与修剪器
Reception Decor=婚宴接待装饰
Reciprocating Saw Blades=往复锯片
Refrigerator Accessories=冰箱配件
Refrigerator Bins=冰箱收纳盒
Regimens and Routines=日常护理方案
Replacement Auto Parts=汽车替换零件
Reptiles=爬宠用品
Resin=树脂材料
Resin Molds=树脂模具
Restored Home=翻新家居商品
Round Head Bolts=圆头螺栓
Safety Glasses=安全防护眼镜
Salad Spinners=沙拉甩干篮
Salt & Pepper Shakers=盐与胡椒调味罐
Saltwater Fishing=海水钓鱼
Sandpaper and Abrasives=砂纸与磨料
Saw Blades=锯片
Scour Pads=百洁布与擦洗垫
Scrapbooking=剪贴簿手工
Scrapers=刮刀
Serving Platters & Trays=餐盘与托盘
Sewing & Cutting Tools=缝纫与裁剪工具
Sewing Storage=缝纫材料收纳
Shade Cloth & Accessories=遮阳网及配件
Shadow Boxes=立体展示框
Sharpeners=磨刀器与磨具
Shoe Racks=鞋架
Shop All Arts & Craft Kits=全部美术与手工套装
Shop All Bar & Wine Accessories=全部酒吧与葡萄酒配件
Shop All Composters=全部堆肥箱
Shop All Craft Vinyl=全部手工刻字贴膜
Shop All Decor=全部家居装饰用品
Shop All Die Cutting=全部模切用品
Shop All Flagpoles=全部旗杆
Shop All Food Storage Containers=全部食品保鲜容器
Shop All Garden Tools=全部园艺工具
Shop All Insoles=全部鞋垫
Shop All Kids' Furniture=全部儿童家具
Shop All Mixers & Attachments=全部搅拌机及配件
Shop All Office Supplies=全部办公用品
Shop All School Supplies=全部学习用品
Shop All Storage Baskets & Bins=全部收纳篮与收纳箱
Shop All Trash Cans=全部垃圾桶
Shop All Wall Decor=全部墙面装饰
Shop All Washer & Dryer Parts=全部洗衣机与烘干机零件
Shop Art Painting Supplies=选购绘画用品
Shop Art Supplies=选购美术用品
Shop Bakeware=全部烘焙器具
Shop Bowls=全部碗具
Shop Curtain Rods=全部窗帘杆
Shop Fills, Foam and Pillows=全部填充材料、泡棉与抱枕芯
Shop Storage Containers=全部收纳容器
Shop all Basic Craft Supplies=全部基础手工材料
Shop all Daily Living Aids=全部日常生活辅助用品
Shop all Massagers=全部按摩器
Shop all Round Head Bolts=全部圆头螺栓
Shop all Storage & Organization=全部收纳与整理用品
Shower Cartridges=淋浴阀芯
Shower Shelving=淋浴置物架
Shower Traps=淋浴排水存水弯
Sink Accessories=水槽配件
Slipcovers=家具防护套
Small Moving Boxes=小号搬家纸箱
Small Pets=小型宠物用品
Smallwares=商用小型器具
Soap Dispensers=皂液器
Soap Dispensing Brushes=可加洗洁精的刷子
Spacer Beads=隔珠
Speciality Crafts & Hobbies=特色手工与兴趣用品
Spice Racks=调味料架
Sports Recovery, Injury Prevention=运动康复与损伤预防
Spray Bottles=喷雾瓶
Sprayers=喷洒器
St. Patrick's Day Decorations=圣帕特里克节装饰
St. Patrick's Day Home Decorations=圣帕特里克节家居装饰
St. Patrick's Day Party Supplies=圣帕特里克节派对用品
Stair Parts=楼梯配件
Stands=支架
Steam Mop Pads & Brushes=蒸汽拖把替换垫与刷头
Steam Tables and Food Wells=保温餐台与水浴保温槽
Steel Wool=钢丝绒清洁球
Steering Wheel Locks=方向盘防盗锁
Stencils & Templates=镂空模板与样板
Step Stools=踏脚凳
Storm & Flood Prep=暴风雨与洪水应急用品
Strength Training=力量训练
String Trimmer Lines=割草机尼龙线
Subscription Household Essential=订阅家庭日用品
Subscriptions=订阅商品
Sugar Bowls & Creamers=糖罐与奶盅
Suncatchers=捕光挂饰
Surf Balance Boards=冲浪平衡训练板
TV & Home Theater=电视与家庭影院
TV Accessories=电视配件
TV Cables & Connectors=电视线缆与连接器
TV Stands=电视柜
TV Stands & Entertainment Centers=电视柜与影音娱乐中心
Table Linens=餐桌布艺
Table Runners=桌旗
Tablecloths=桌布
Tea Kettles=茶壶
Teaching Aids=教学辅助用品
Teaching and Classroom Supplies=教学与教室用品
Teens' Bathroom=青少年浴室用品
Teens' Rooms=青少年房间用品
Tennis Training Aids=网球训练辅助器
Tent Accessories=帐篷配件
Tent Guylines=帐篷防风绳
Tents=帐篷
Terrarium Planters=微景观植物盆
Thanksgiving Dessert & Treat Decorating=感恩节甜点装饰用品
Thanksgiving Party Supplies=感恩节派对用品
Thread and Fabric Storage=线材与布料收纳
Tire Inflators with Gauge=带压力表的轮胎充气泵
Tissue Box Cover=纸巾盒罩
Toilet Brushes=马桶刷
Toilet Installation Kits=马桶安装套件
Toilet Paper Holders=卫生纸架
Toiletry Bags=洗漱包
Towel Racks=毛巾架
Trading Card Binders & Sleeves=收藏卡活页夹与保护套
Trading Cards=收藏卡
Transfer Papers=转印纸
Travel Drinkware=旅行饮具
Travel Pillows=旅行枕
Travel Wallets=旅行证件钱包
Trimmers and Edgers Parts and Accessories=割草修边机零件与配件
Truck Bed Accessories=皮卡车货箱配件
Truck Bed Organizers=皮卡车货箱收纳用品
Truck Bed Rail Caps=皮卡车货箱栏板盖条
Turkey & Meat Basters=火鸡及肉类浇汁器
Turtles=宠物龟用品
Umbrella Racks & Stands=雨伞架
Universal Seat Covers=通用座椅套
Vacuum Accessories & Parts=吸尘器配件与零件
Vases=花瓶
Ventilation=通风用品
Wall Hangings=墙面挂饰
Wall Organization=墙面收纳
Wall Plates=墙壁面板
Wall Shelves=墙面置物架
Wall-Mounted Hose Reels=壁挂式水管卷盘
Walmart Restored=沃尔玛翻新商品
Walmart Restored Cooling and Heating=沃尔玛翻新制冷与供暖设备
Walmart Restored Small Appliances=沃尔玛翻新小家电
Watch Boxes=手表收纳盒
Watches=手表
Water Bottles=水壶
Water Heaters=热水器
Waterproof Outdoor Furniture Covers=防水户外家具罩
Waterproof Tape=防水胶带
Wedding Accessories=婚礼配件
Wedding Party Supplies=婚礼派对用品
Wedding Party Tableware=婚礼派对餐具
Weight Lifting Accessories=举重配件
Weight Lifting Equipment=举重装备
Weight Storage=健身配重器材收纳
Weight Training Accessories=力量训练配件
Weights=健身负重器材
Wet=湿用类别（源类目不完整）
Wheel Accessories=车轮配件
White Poster Board=白色海报板
White Zip Ties=白色扎带
Wicker Laundry Baskets=藤编洗衣篮
Wildfire Prep=野火应急用品
Wind Chimes=风铃
Window Screens and Films=窗纱与玻璃贴膜
Window Weatherstripping=窗户密封条
Wine Aerators & Pourers=葡萄酒醒酒器与倒酒器
Wine Racks=酒架
Wipe Warmers & Holders=湿巾加热器与收纳架
Womens Clothing=女装
Womens Coats=女士外套
Womens Faux Fur Coats=女士仿皮草外套
Womens Hair Accessories=女士发饰
Womens Jewelry=女士珠宝首饰
Womens Jewelry & Watches=女士珠宝首饰与手表
Womens Rings=女士戒指
Wood Coffee Tables=木质茶几
Wood Crates=木箱
Wood End Tables=木质边几
Wood Floating Shelves=木质悬浮置物架
Wooden Easels=木质画架
Wool Dryer Balls=羊毛烘干球
Yarn & Needle Arts=毛线与针线手工艺
Yoga Blocks=瑜伽砖
Yoga Mats=瑜伽垫
Zip Tie Colors=扎带颜色
browse subscription food prep and storage=订阅商品：食品准备与收纳
shoe storage=鞋子收纳
"""


def translate_category(value: object) -> str:
    """Translate known category terms offline, retaining explicit unknowns."""
    if value is None or not str(value).strip():
        return "未分类"
    raw = re.sub(r"\s+", " ", str(value)).strip()
    exact_name = _EXACT_CATEGORY_PATH_ZH.get(raw) or _V6_EXACT_CATEGORY_PATH_ZH.get(raw)
    if exact_name is not None:
        return exact_name
    if re.search(r"[\u3400-\u9fff]", raw):
        return raw
    normalized = _normalize(raw)
    direct = _CATEGORY_ZH.get(normalized)
    if direct:
        return direct
    # The provider sometimes returns an English breadcrumb path. Translate
    # every segment exactly; unknown segments are NOT dropped or fabricated.
    parts = re.split(r"\s*(?:>|\||\\|/|»|›)\s*", raw)
    if len(parts) > 1:
        resolved = [_CATEGORY_ZH.get(_normalize(part)) for part in parts if part.strip()]
        if resolved and all(resolved):
            return " / ".join(resolved)
    return "待补充中文分类"


# NP_BOARD_BUSINESS_CATEGORY_V5: separate aggregate identity from raw taxonomy.
# The full breadcrumb is translated per segment and never used as a group key.
_V5_SEGMENT_ZH = dict(line.split("=", 1) for line in _V5_SEGMENT_TRANSLATIONS.strip().splitlines())
_V5_SEGMENT_ZH.update(
    {
        "Kitchen Tools & Gadgets": "厨房工具与小配件",
        "Tools & Gadgets": "工具与小配件",
    }
)


def category_path_detail(raw: str) -> dict[str, str]:
    """One raw source path -> one traceable two-line tooltip pair."""
    raw = str(raw or "").strip()
    if not raw:
        return {"raw": "", "zh": "", "label": "来源分类缺失"}
    if re.search(r"[\u3400-\u9fff]", raw):
        return {"raw": raw, "zh": raw, "label": raw.split(" > ")[-1]}
    parts = [part.strip() for part in raw.split(" > ")]
    exact = _EXACT_CATEGORY_PATH_ZH.get(raw) or _V6_EXACT_CATEGORY_PATH_ZH.get(raw)
    resolved = []
    for index, part in enumerate(parts):
        value = _V5_SEGMENT_ZH.get(part) or _CATEGORY_ZH.get(_normalize(part))
        if index == len(parts) - 1 and exact is not None:
            value = exact.split(" / ")[-1]
        if not value:
            return {"raw": raw, "zh": "待补充中文分类", "label": "待补充中文分类"}
        resolved.append(value)
    return {"raw": raw, "zh": " > ".join(resolved), "label": resolved[-1]}


def business_category(raw: str) -> str:
    """One raw category -> exactly one stable Chinese aggregate group."""
    raw = str(raw or "").strip()
    if not raw:
        return "未分类"
    if raw in {"Kitchen & Dining", "厨房与餐饮"}:
        return "厨房用品"
    if re.search(r"[\u3400-\u9fff]", raw):
        return raw.split(" / ", 1)[0]
    parts = raw.split(" > ")
    if category_path_detail(raw)["zh"] == "待补充中文分类":
        return "待补充中文分类"
    root = parts[0]
    second = parts[1] if len(parts) > 1 else ""
    third = parts[2] if len(parts) > 2 else ""
    # NP_LISTING_ALL_CATEGORY_V6: source-scoped practical business groups.
    if root == "Office Supplies" and second == "Moving":
        return "搬家包装"
    if root == "Household Essentials" and second == "Bathroom Cleaning Supplies":
        return "清洁用品"
    if root == "Home Improvement" and second == "Bathroom Renovation":
        return "水暖卫浴"
    if root == "Home" and second in {"Kids' Rooms", "Teens' Rooms"}:
        return "儿童家居"
    if root == "Home" and second == "Bedding":
        return "床上用品"
    if root == "Home":
        if second == "Kitchen & Dining":
            return "厨房用品"
        if second == "Appliances" and third == "Kitchen Appliances":
            return "厨房用品"
        if second == "Storage & Organization":
            return "家居收纳"
        if second == "Appliances":
            return "家用电器"
        if second == "Bath":
            return "浴室用品"
        if second in {"Decor", "Holiday Decor"}:
            return "家居装饰"
        if second == "Luggage":
            return "旅行用品"
        if second == "Furniture":
            return "家具用品"
        return "家居用品"
    if root == "Home Improvement":
        if second in {"Hardware", "Tools", "Electrical", "Doors and Gates"}:
            return "五金工具"
        if second == "Plumbing":
            return "水暖卫浴"
        return "家居装修"
    if root == "Household Essentials":
        return "清洁用品" if second == "Cleaning Supplies" else "家居日用"
    return {
        "Arts Crafts & Sewing": "手工艺用品",
        "Auto & Tires": "汽车用品",
        "Baby": "母婴用品",
        "Beauty": "美妆个护",
        "Clothing": "服饰配件",
        "Electronics": "电子数码",
        "Health and Medicine": "健康护理",
        "Industrial & Scientific": "工业商用",
        "Musical Instruments": "乐器配件",
        "Office Supplies": "办公用品",
        "Party & Occasions": "派对节庆",
        "Patio & Garden": "庭院园艺",
        "Personal Care": "美妆个护",
        "Pets": "宠物用品",
        "Sports & Outdoors": "运动户外",
        "Toys": "玩具用品",
        "Collectibles": "收藏卡牌",
        "Food": "食品杂货",
        "Jewelry": "珠宝手表",
        "Subscriptions": "订阅商品",
        "Walmart for Business": "工业商用",
    }.get(root, "待补充中文分类")

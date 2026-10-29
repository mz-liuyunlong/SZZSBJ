# 打包审批 GTIN 标签入口

状态：需求整理；2026-10-28，尚未批准 PRP 或实现。

## FEATURE / UI REQUIREMENTS
PMC 国内仓打包单审批的 GTIN 列显示号码及“标签”，点击新标签页预览可下载的 PDF，参照用户截图。ItemID 商品链接独立完成。

## BUSINESS RULES / DATA SOURCE
标签身份随当前目标店铺和 ItemID；GTIN 保留前导零，不能按 SKU 猜测。使用新系统候选及 dim_walmart_listings，不读取旧库，不复制旧代码。旧样式参考为 50×30 mm、Code128、完整 14 位 GTIN、MSKU、Made in China。

## PERMISSION / API REQUIREMENTS
沿用页面读取权限与来源账号范围；新增只读标签能力的具体接口见 PRP。缺失或失效身份不可生成错误标签。

## TESTS / DOCUMENTATION / FORBIDDEN
覆盖来源权限、身份版本、GTIN 校验、PDF 尺寸及条码解码、前端打开和失败提示。更新 API 文档、SOP、registry、handoff。不改审批、OWS、库存、生产或旧项目。

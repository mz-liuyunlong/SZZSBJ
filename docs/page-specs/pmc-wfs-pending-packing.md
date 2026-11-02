# 待发货打包单页面规格及组件复用

路径 `/pmc/wfs/pending-packing`，沿用PMC/WFS侧栏。页面状态testing，数据来源new_postgres；其他WFS页面仍为各自原状态。

PageShell统一标题动作及新标签页帮助；ProTable主表按PK分页，展开Table按稳定装箱行勾选。复用ManagementStatCards、CommittedSearch、ResetButton、WalmartItemLink；保留现有PendingPackingPage.css布局。查询和API/type分文件，不引入依赖。

列为选择、PK/测试/完成信息、店铺/换链接、SKU/品名、ItemID/GTIN、审批/实装数量、报关、实际装箱/改箱、可建状态和阻断原因；未设置OWS必填列。展开显示行号、箱数、每箱件数及占用。

筛选：完整可见范围的店铺选项、提交式关键字、业务测试；筛选/分页/刷新清除勾选。统计独立查询全部匹配PK而非当前页。Loading/Empty/Error/重试明确区分，不失败后回退mock。

PendingDraftDialog负责地址及草稿组确认，PendingIdentityDialog负责最新单据及Listing证明；改箱、报关复用现有PackingWarehouseActionDialog。失败不关闭表单，写请求按签名保持幂等键，成功刷新两侧查询。所有变更按钮按动作权限隐藏/禁用，当前草稿占用时变更禁用。

前端查询键包含登录用户名scope，路由传入真实权限；后端仍独立验证身份、来源账号及店铺范围。当前阶段不出现审批或外部执行动作。

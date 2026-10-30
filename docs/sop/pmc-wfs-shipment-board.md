# WFS 货件看板 SOP（M2）

## 用途

查看公司全部 WFS 货件（领星 `queryWFSCargoPage` 同步）及每票走到哪一步：待发货 / 在途 / 收货中 / 已关闭 / 已取消，申报 / 发出 / Received / 破损数量，发货仓、物流、实际发货、到港（领星 SP 发货单）。本系统创建但领星尚未出现的票显示「待领星同步」。Walmart 侧签收 / Receipt 逐件数据由后续切片接入。

## 操作

1. 打开 PMC → WFS → **WFS 货件看板**。顶部横幅显示领星数据时间，超过 24 小时变黄。
2. 点统计卡（在途 / 收货中 / 已关闭 / 待领星同步 / 测试）即按该条件筛选；也可用店铺、状态下拉和关键字（货件号 / 入库单号 / 发货单或运单 / PK / MSKU / SKU / Item / GTIN）。
3. 点行打开详情：节点时间线、商品行与合计、领星发货单、本系统创建记录、关联异常。
4. 「产品维度」按 店铺 × MSKU 汇总当前筛选下的申报 / 发出 / Received / 破损 / 在途。

## 数据刷新（手工，由负责人授权）

1. 首次：`PMC_WFS_GOVERNANCE_BOOTSTRAP_AUTHORIZED=true PMC_WFS_SOURCE_ACCOUNT_REF=<账号> uv run python scripts/bootstrap_pmc_wfs_board_governance.py`，然后在治理表把两条接口的 `outbound_enabled` 和配置的 `is_enabled` 打开（不开 schedule）。
2. 拉数 + 发布（只能在 company-ai 上跑：领星按 IP 白名单放行；开发库用反向隧道，见交接册第 70 章）：`PMC_WFS_ONE_TIME_RUN_AUTHORIZED=true PMC_WFS_SOURCE_ACCOUNT_REF=<账号> PMC_WFS_PUBLISH_AFTER_RUN=true uv run python scripts/run_pmc_wfs_board_once.py`（默认窗口 2026-05-01 → 今天；需要 `LINGXING_ENABLE_REAL_CALLS=true` 等真实调用开关；`LINGXING_TIMEOUT_MS` 建议 120000，发货单接口 200/页会超时，配置默认 50/页）。
3. 只重发布不拉数：`PMC_WFS_BOARD_PUBLISH_AUTHORIZED=true uv run python scripts/publish_pmc_wfs_board.py --source-account <账号> --latest`。

## 说明

- 横幅显示「领星数据尚未同步到看板」= 还没有发布版本，列表只会有本系统创建的待同步票。
- 「待领星同步」行在下一次拉数后自动变为领星行；若长期不出现，说明 Walmart 侧创建未被领星收录，需人工核查。
- 看板不写领星、不调 Walmart。

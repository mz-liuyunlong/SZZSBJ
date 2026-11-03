# PMC WFS › 设置 · 接口数据源决策

- 业务用途：保存 WFS 时效 / 提醒规则、店铺设置、FC 地区映射、创建货件默认值，供异常中心与创建表单读取
- 需求来源：8088 DEMO `features/pmc-wfs-shipment/drafts/src/app-d.jsx` `TabSettings`、`app-a.jsx` `STORE_SETTINGS_INIT`、`app-b.jsx` `CREATE_DEFAULTS_INIT`
- 后续接口 PRP：`PRPs/pmc-wfs-settings.md`
- 总体状态：`READY_FOR_PRP`（全部是本系统自有配置或复用已同步数据；待负责人选 PRP §0 S1–S5）

## 1. 旧系统与来源调查

| 项 | 现状 |
|---|---|
| 8088 | 七块全在页面内存，刷新恢复；不读库、不调接口；物流商 / 渠道字典来自领星「查询头程物流渠道列表」票据回传（61 条） |
| 5173 | `WfsSupportPages.tsx` 三个数字，只存本页 |
| #284 分支 | `ops_wfs_store_settings`（0072）+ `GET/PUT /api/pmc/wfs/settings/stores`，开发库已录八店 |

## 2. 数据集分类表

| # | 数据集 | 当前权威来源 | 分类 | 策略 | 需负责人确认 |
|---|---|---|---|---|---|
| W1 | 时效 / 提醒规则（11 条默认） | 8088 页面常量 | NEW_SYSTEM_OWNED（`ref_wfs_rule_setting_versions` / `ref_wfs_rule_settings`） | 迁移种子 = 8088 默认；版本化 | 是（S2 / S3） |
| W2 | 店铺 Walmart 代码、ITS、可创建开关 | #284 `ops_wfs_store_settings` | NEW_SYSTEM_OWNED | 从 #284 摘出 | 是（S1） |
| W3 | 店铺联系人、设施名、电话、邮箱 | 8088 页面（空白，本系统维护，不传 Walmart） | NEW_SYSTEM_OWNED | 加列 | 否 |
| W4 | 发货地址簿（历史货件退货地址去重） | 领星 WFS 货件 | REBUILD_SYNC（复用 WFS 组 S1 ODS） | 只读 | 否 |
| W5 | FC 代码 / 邮编 / 城市 / 州 | 领星货件 logistics_code 与收货地址 | REBUILD_SYNC（复用） | 种子 + 只读字段 | 否 |
| W6 | FC 地区（美西 / 美中 / 美东） | 公司自定义 | NEW_SYSTEM_OWNED（`ref_wfs_fc_regions`） | 可改 | 否 |
| W7 | 创建货件默认值 | 8088 常量（Rocky 2026-09-22） | NEW_SYSTEM_OWNED（`ref_wfs_creation_defaults`） | 可改 | 否 |
| W8 | 物流商 / 渠道字典 | 领星头程物流商 / 渠道 | REBUILD_SYNC（WFS 组 S3 `dim_logistics_channels`） | 只读 | 否 |
| W9 | 通知渠道开关 | 8088 界面 | 不做 | — | 是（S4） |
| W10 | 上架缓冲天数 | 自动补货规则 | 引用（不另存） | 只读显示 | 是（S5） |

## 3. 风险检查

- [x] 不调任何外部接口；不写 RAW / ODS
- [x] 每次修改记操作人、时间、原因，历史版本不删
- [ ] #284 摘取时需确认不带出 Walmart 建货件代码（S1）
- [ ] 8088 标「示例」的 5 条阈值未经 Rocky 定值（S3）

## 负责人决定

（待填写 PRP §0 S1–S5）

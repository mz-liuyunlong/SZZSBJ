# SKU进度列表 / 统计 / 筛选及前端接入（0100）

负责人已确认独立汇总、自动刷新外部字段、列表/统计/下拉/日期/多选/排序及现有前端接入，禁止修改样式。沿用首批采购固定20件及审批工作台限制。实施候选，未部署。GitHub 核查 main `ae4a8cb8fb84ff3cb9f11c39a76c4adb3268a068`；增量安装以本地前序交付源码的哈希为准，不切换分支。

## 权威来源和口径
- 已同步 SKU 当前快照、小批量测品标签、0100扩展开发日期、Listing MART、广告状态 MART；定时刷新只更新 `mart_new_product_sku_progress_current` 源投影，继续使用原600秒生产可控任务。背景刷新沿用已发布 monitor RAW event 主键获取划线价标志；列表/统计/选项不读取 RAW，不调用领星。Listing负责人沿用其 MART `owner_ref`，真实姓名映射仍待验收。开品日期按 Asia/Shanghai 转为日期；Listing日期取精确账号/店铺/Item/MSKU 的 `listing_wfs_first_stock.launch_date_cn`，不推算。
- SKU自身的业务记录只读关联；备注、推进、采购、独立站不被刷新任务覆盖。PMC 只按本次真实计划单号、账号、店铺及 SKU 匹配，避免同一采购计划中的其他SKU误归属；不把历史采购推断为首批采购。
- 国内发货权威来源未确认，本次返回 null、显示待确认，筛选已/未发货均为0；不得假造未发货。广告仍沿用0100已核实证据和48小时新鲜度；未知不等于关闭。独立站展示已存在 SKU/Listing 业务记录，不新增写操作，不决定最终业务粒度。
- 同一账号范围、按SKU分页；多选同维度 OR、跨维度 AND，SKU内存在匹配Listing即匹配SKU，保留组内所有Listing。店铺/负责人/开发人员采用账号+身份组合值，展示真实源标签。选项计数排除自身筛选，按SKU去重；日期边界排除日期本身，其他条件有效。统计卡忽略当前卡片本身的筛选，保留更多筛选。排序白名单、稳定ID二级排序。查询源与 IAM scope 使用同一只读 session。

## API及前端
- `GET /api/new-products/sku-progress/list`：page, page_size(1..100), sort_by(date/product/name/dev/progress/listing), sort_order, search_field(all/sku/name/item), keyword, card(all/active/done/paused/terminated), start/end 和11个重复多选参数(store/owner/developer/listing/plan/site/strike/ad/proc/ship/progress)。返回 items,total,listing_count,page,page_size；嵌套 listings/purchase_plans/independent_site_submissions；采购候选只是只读提示，后端提交重验全部门禁。
- `GET .../summary`：同条件、无分页，返回各推进统计、SKU及Listing数。
- `GET .../facets`：同条件、无分页，返回11维 facets `{value,label,count}` 和 `date_range {min,max}`，`unknown_sources` 说明未验证来源。
- `POST .../purchase`：复用上一版，单个SKU弹窗接入；只允许固定20件及已上架、符合已确认等级/风险、Item ID、GTIN、SID等原有门禁。仍须独立启用开关，保留原审批工作台权限、防重和回执校验。不自动真实提交。批量采购及备注/独立站/推进状态写入口不是本轮范围。
- 前端取消全量加载及浏览器分页；独立 query keys，分页和排序只请求列表，筛选变化刷新需要的接口，更多筛选草稿单独获取选项，每60秒后台刷新活动查询。保留原组件、15列名称顺序宽度、CSS、弹窗和布局，排序指示符为新增功能的默认组件行为。保留原来禁用的批量选择及备注写操作，不改变样式或擅自开通业务操作。

## 验证边界
本地隔离测试通过，SQLAlchemy PostgreSQL 编译及模拟 HTTP 测试通过，前端适配器 strict TypeScript 检查、模拟传输、TSX语法检查和样式差异检查通过。容器无 PostgreSQL 服务及完整项目依赖，网络无法获取缺失依赖；全仓 CI、真实 SQL 执行计划、真实前端构建/渲染及生产数据验收尚未完成。无迁移、真实采购、数据写入、生产配置、Git操作。安装器严格检查旧哈希，发现冲突即停止。

## 生产发布及回滚保护（本轮合并前修复）

- SKU进度在新品表现的生产构建和开发构建均显示；打品跟踪不增加此入口，原布局及CSS不变。
- 0100先执行正式迁移，再按现有发布流程更新 API、Worker、Beat 与前端。生产默认每600秒刷新SKU源投影；明确设置 `SZZSBJ_SKU_PROGRESS_REFRESH_ENABLED=0` 可暂停，非生产不自动运行。Beat 与 Worker 使用同一个开关判断；不新增队列。第一次计划任务运行完成后核对投影行数、任务状态和页面统计，不能把尚未同步的来源当作真实空数据。
- 首次投影使用已经存在的小批量测品SKU、Listing和已发布广告证据；历史扩展字段需要时按 `sku-ad-foundation-runtime-0100.md` 单独审批、按范围回放，不自动补造历史或调用第三方。未完成来源同步时仍可能有未知字段。
- 不自动开启 `SZZSBJ_SKU_PROGRESS_PURCHASE_ENABLED`，不执行真实采购；跨采购流程防重问题仍须另行审核。
- 0100回滚前在同一事务锁住所有16张新表，任何一张有数据即拒绝降级，保持表和数据；只有全部为空才可删除新表。已产生数据时使用代码回退/前向修复，不删除业务历史。未执行生产迁移、回填或服务重启。

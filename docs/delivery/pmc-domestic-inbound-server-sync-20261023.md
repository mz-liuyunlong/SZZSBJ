# 国内仓批次看板服务器核查与同步记录

日期：2026-10-23。状态：原程序同步、发布及线上读取服务验收完成；未做实际登录页面验收。

## 授权

负责人明确要求先连接服务器核实批次看板数据来源与存储，再通过原同步程序写入真实数据。此次采用原程序重新采集，不实施先前候选 RAW 恢复工具开发方案。不改代码版本、分支、本地 .env、生产服务或部署配置，不重启服务，不向领星或 Walmart 写业务数据。

## 线上实际链路

- SSH 已连通，主机名 VM-0-6-ubuntu。
- 8443 的 API 由 Nginx 转发到 127.0.0.1:8010。
- 后端服务 szzsbj-backend，进程核查时 PID 11318。
- 实际工作目录：`/opt/szzsbj/releases/1a9a44778effd4c8e4960b7b8d4f55aaa74e1314/source/backend`。
- 使用进程已加载的环境，不输出凭据；数据库目标为服务器 127.0.0.1:5432/szzsbj_app，schema public，应用角色 szzsbj_app_user。
- GET `/api/pmc/domestic/inbound-batches` 查询 gov_domestic_board_publications 当前 published 版本及 mart_domestic_inbound_batch_board。
- W1 写 ods_lingxing_domestic_batches，W3 写 ods_lingxing_domestic_warehouse_statements。采集后还需发布，不是采集成功即页面可见。

## 实际预检

应用角色只读查询确认上述四张业务表各 0 行。数据库版本为 20261022_0054_merge_walmart_identity_and_domestic_packing，无需先执行迁移。

历史成功 W1 run aafbbf09-e245-4056-a83a-232dd1d87dff，历史成功 W3 run 3d7f1c80-183a-44da-a334-7758c764e02b。线上原 parser 对保留 RAW 做内存重放，得到 W1 4 页 1528 行、W3 7 页 1264 行，非惠州仓行数均 0；该步骤没有写数据库，也没有调用领星。

两项治理接口和 primary 同步配置均 disabled，周期调度均 false，无 queued/running 领星任务。原一次性同步入口和发布入口均已部署。

运行环境 LINGXING_ALLOW_STRUCTURED_WRITE=true，而原国内仓一次性 runner 要求 false。首次只收窄此开关时触发 SettingsError，发生在写入前；只读复查确认没有新任务、没有操作报告，两项接口及配置仍 disabled。随后在独立同步子进程同时关闭 LINGXING_ALLOW_STRUCTURED_WRITE、LINGXING_ENABLE_BATCH_PRODUCT_INFO_REQUESTS、PRODUCTLIST_REAL_SYNC_AUTHORIZED、DATA_PAGES_REAL_SYNC_AUTHORIZED，配置校验通过。不更改 .env、不影响运行服务。该 runner 自身按既有代码写国内仓 ODS。

## 拟执行范围

仅 primary、惠州仓 16168。W1 为包含零库存的完整批次快照；负责人最终确认 W3 保持 30 天，即 2026-09-23 至 2026-10-23（结束不含）。期间曾提出 10 天方案，但在同步开始前已撤回，没有执行 10 天采集。一次仅开启一个接口，完成或失败后恢复原开关，不启用定时任务。

保留已有 RAW、任务和引用；新增本次成功或失败任务审计。仅成功且完整的来源 run 可用于原发布器，来源时区按历史确认为 Asia/Shanghai，发布保留版本并原子切换当前标志。

## 备份与结果

同步前全库备份：`/opt/szzsbj/backups/pmc-inbound-sync-20261023T120110Z/before-sync.dump`，3551385597 字节，SHA256 `ad546833d5817511f801af0838ec5a020ed765415d8046bccc4546530f0ecd06`。目录权限 700、备份文件权限 600。pg_restore 目录校验通过；未做全库恢复演练。备份留在服务器，没有下载到本地。

原一次性 runner 实际执行于 2026-10-23 20:17:31 至 20:18:00（Asia/Shanghai），未修改部署代码：

| 来源 | 本次 run | 结果 | 写入数 |
|---|---|---|---:|
| W1 | 7408166b-40ad-48b3-acc2-94d14980c783 | succeeded | 1571 |
| W3 | 3e5b5219-3ffd-4bc9-bfeb-0e689b9f1132 | succeeded；2026-09-23 至 2026-10-23，结束不含 | 1281 |

两项 duplicates_skipped 均 0。原 builder 基于本次 ODS 只读生成候选 1480 行，涉及 1394 个入库单、770 个 SKU；全部候选通过现有 InboundRow schema 校验。

随后调用服务器原 `scripts/publish_pmc_domestic_inbound.py`，指定上述成功来源 run、primary、16168、Asia/Shanghai。2026-10-23 20:19:27（Asia/Shanghai）发布成功：

- publication：d0a8732d-7bfe-4f32-b8ad-ba960c5706af。
- 唯一目标当前版本 status=published、is_current=true，MART 1480 行。
- 来源观察时间为 2026-10-23 20:17:34（Asia/Shanghai）。
- 原线上 InboundReadService 实际读取 data_status=ready、total=1480、首屏 50 行。
- 列表、统计、筛选项使用同一 publication；店铺选项 9、负责人选项 12。
- 统计：入库单 1394、SKU 770、批次余额 8351、已知父级入库量 26574；历史父级入库量未知 1224 组，未补零；缺到仓日期 0。
- 接口开关、配置开关、schedule_enabled 均恢复 false；国内仓 queued/running 任务为 0。
- Alembic 版本保持 20261022_0054_merge_walmart_identity_and_domestic_packing；后端服务未重启。

脱敏操作记录：同一备份目录内 manifest.json、sync-result.json、publish-result.json。工具使用进程已加载环境，未把凭据写入记录。

验收边界：已验证生产数据库和原读取服务，不宣称已验证真实登录态 HTTP 或浏览器页面。负责人可刷新线上批次看板确认。此次使用新采集数据重建展示，不恢复或覆盖历史成功 run；为什么旧 ODS 与发布记录为空尚未确定，需要另查清理、恢复和运维审计。

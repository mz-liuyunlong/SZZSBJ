# DEPLOY_LEDGER（部署台账 · 只追加）

> 用途：CODE_DEPLOY_SOP §3.11.7 的核心物证。每单部署放行后，由部署AI在本文件**追加一行**。
> 判据：生产任何受管文件（src/ admin-frontend/src/ sql/ context/）的当前 md5，必须能被「基线 + 本台账各行」解释；
> 解释不了 = 未走流程的改动 → 一致性哨兵报警 / 需求方追查。
> 纪律：**只追加，不改写历史行**（§3.9.1 锚点纪律同源）；台账行与审查回执（_deploy_tmp/audit/）一一对应。
> **行规范（2026-08-24 哨兵首跑实证后固化）**：「文件」列必须逐个写**完整仓库相对路径**（多文件用 + 分隔）。
> 哨兵按完整路径/完整文件名做全文匹配，简写（如 sql/015）必然误报；历史简写行不改写，用补登行豁免。
>
> **零号基线**：`context/DEPLOY_BASELINE_20260824.tsv`（2026-08-24 第2轮只读探测的生产全量 md5 清单，
> 379 个文件，源=_deploy_tmp/prod_snapshot_20260824/md5_prod.tsv，基线文件自身 md5=e451a46e5450c0f7e9160ca167c303b7）。
> 基线时点已知在途分叉（探测已取证，后续单据逐一收敛，收敛时在下表登记）：
> ①ClearanceCenter.tsx 生产领先Mac ②sql/015 Mac领先 ③syncLingxingDailyToDb.ts Mac领先(msku加固)
> ④CODE_DEPLOY_SOP.md Mac领先(§3.11) ⑤only_mac 7个SQL待归档到生产 ⑥生产10个._垃圾待清。

| 日期 | 模块 | 文件 | Mac_md5 | 生产目标_md5 | 是否重启 | 回执路径 |
|---|---|---|---|---|---|---|
| 2026-08-24 | 台账零号基线 | （全量379文件见基线tsv） | — | — | 否 | _deploy_tmp/prod_snapshot_20260824/（第2轮探测回执） |
| 2026-08-24 | context同步·§3.11生效 | CODE_DEPLOY_SOP.md + DEPLOY_LEDGER.md + DEPLOY_BASELINE_20260824.tsv | 见本行下方文件级md5 | 同Mac | 否 | _deploy_tmp/audit/20260824_context_sync_audit.txt |
| 2026-08-24 | msku空串加固 | src/syncLingxingDailyToDb.ts | 2a8f0004ce606c4ba9930f0f41571d8b | 2a8f0004ce606c4ba9930f0f41571d8b | 否 | _deploy_tmp/audit/20260824_msku_deploy_audit.txt |
| 2026-08-24 | sql归档补齐 | sql/015(覆盖)+sql/025+sql/031+sql/032(新增) | 84ce883e/9134e49a/e6877814/a0fdeac3(前8位) | 同Mac | 否 | _deploy_tmp/audit/20260824_sql_archive_audit.txt |
| 2026-08-24 | AppleDouble隔离 | 10个._文件 → _appledouble_quarantine_20260824/ | — | — | 否 | _deploy_tmp/audit/20260824_appledouble_audit.txt |
| 2026-08-24 | 一致性哨兵部署(未挂cron) | src/checkDeploySyncSentinel.ts + context/DEPLOY_BASELINE_CRON.txt | 66ebf627/de9d822b(前8位) | 同Mac | 否 | _deploy_tmp/audit/20260824_sentinel_deploy_audit.txt |
| 2026-08-24 | 台账规范修正·误报补登(零部署动作) | sql/015_event_clearance_approval.sql + sql/025_dim_product_walmart_status.sql + sql/031_attendance_tables.sql + sql/032_help_attendance.sql（为「sql归档补齐」行补登完整文件名，哨兵按完整名匹配豁免） | 同「sql归档补齐」行 | 同Mac | 否 | _deploy_tmp/audit/20260824_sentinel_deploy_audit.txt（根因诊断在此） |
| 2026-08-24 | 哨兵挂cron·台账修正同步 | context/DEPLOY_LEDGER.md + context/DEPLOY_BASELINE_CRON.txt + crontab新增deploy-sync-sentinel(06:40) | a1707c39/60e901c6(前8位) | 同Mac | 否 | _deploy_tmp/audit/20260824_sentinel_cron_audit.txt |
| 2026-08-24 | 第七单·三态改造(部分·跳过TASK_CHANGE_LOG.md) | src/buildOpsActionLogDaily.ts + src/syncAdsConfigSnapshotDaily.ts + sql/085_ops_action_log_group_matchtype.sql + context/API_MAP.md（TASK_CHANGE_LOG.md 跳过的：票内目标236c351e不在git历史，Mac现版3d936dc8/MM态；依override跳过）+ crontab 91→94(5处变更) | 8b6aee08/4e4e3fcc/695fec63/7b8d7892(前8位) | 同Mac | 否 | _deploy_tmp/audit/20260824_第七单_三态改造上线_audit.txt |
| 2026-08-24 | 第七单补丁·TCL同步与兜底cron | context/TASK_CHANGE_LOG.md + crontab 94→95(新增0 21兜底行) | 3a4fb674→bbc6cdf6 | 同Mac(bbc6cdf6) | 否 | _deploy_tmp/audit/20260824_第七单补丁_TCL同步与兜底cron_audit.txt |
| 2026-08-24 | 广告费报表1001拆行归因+纯数字精确搜索 | src/adsFeeReportRoutes.ts + admin-frontend/src/AdsFeeReport.tsx | 78a92797/a2174dc3(前8位) | 同Mac | 是(lingxing-admin) | _deploy_tmp/audit/20260824_adsfee1001_audit.txt |
| 2026-08-24 | 第八单·系统运营日志展示格式重排 | src/feishuRawSalesRoutes.ts + src/salesDetailV2Routes.ts + context/TASK_CHANGE_LOG.md（TCL目标修正为9941a3a7，原票66835667过期） | e5ab1777/e66d08be/9941a3a7(前8位) | 同Mac | 是(lingxing-admin) | _deploy_tmp/audit/20260824_第八单_展示格式上线_audit.txt |
| 2026-08-25 | 按品广告费统一口径(素材钱并入商品) | src/adsItemSpendAlloc.ts + src/adsFeeReportRoutes.ts + src/orderProfitV2Routes.ts + src/aiFinanceRoutes.ts | c9d8cade/0c0631cf/b0c6d87d/afee95c5(前8位) | 同Mac | 是(lingxing-admin) | _deploy_tmp/audit/20260825_alloc_deploy_audit.txt |
| 2026-08-25 | SBSV页统一口径(asin-kw-mvp后端) | _asin_kw_mirror/walmart_sbsv/router.py → /opt/asin-kw-mvp/backend/walmart_sbsv/router.py | 51b05dfe(前8位) | 51b05dfe(前8位) | 是(asin-kw-backend) | _deploy_tmp/audit/20260825_sbsv_deploy_audit.txt |
| 2026-08-25 | 事故处置·SBSV慢查询修复(视图烤入platform+campaign_type六处限定) | _asin_kw_mirror/walmart_sbsv/router.py → /opt/asin-kw-mvp/backend/walmart_sbsv/router.py | d55d2720(前8位) | d55d2720(前8位) | 是(asin-kw-backend) | _deploy_tmp/audit/20260825_sbsv_incident_audit.txt |
| 2026-08-25 | 单10回滚(视图性能事故止血) | src/adsFeeReportRoutes.ts + src/orderProfitV2Routes.ts + src/aiFinanceRoutes.ts | 78a92797/5fd5fdc4/1b42947c(前8位,回滚至) | 同左 | 是(lingxing-admin) | _deploy_tmp/audit/20260825_unit10_rollback_audit.txt |

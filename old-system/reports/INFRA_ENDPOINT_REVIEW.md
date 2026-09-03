# 基础设施端点复查

只输出路径和风险类型，不输出域名、IP、密钥、完整 Token 或数据库连接串。

| 文件路径 | 风险说明 | 风险等级 |
|---|---|---|
| `AI经营分析报告/generate_weekly_report_manual.py` | IP 地址 | 高 |
| `AI经营分析报告/generate_weekly_report_manual.py` | 基础设施配置字段 | 中 |
| `AI经营分析报告/正式系统/BusinessAnalysis.tsx` | 内部/API 路径 | 中 |
| `AI经营分析报告/正式系统/aiBusinessRoutes.ts` | IP 地址 | 高 |
| `AI经营分析报告/正式系统/aiBusinessRoutes.ts` | 基础设施配置字段 | 中 |
| `AI经营分析报告/正式系统/交付件/App.tsx` | 内部/API 路径 | 中 |
| `AI经营分析报告/正式系统/交付件/BusinessAnalysis.tsx` | 内部/API 路径 | 中 |
| `AI经营分析报告/正式系统/交付件/FeishuRawSalesData.tsx` | 内部/API 路径 | 中 |
| `AI经营分析报告/正式系统/交付件/MonthlyPlanPanel.tsx` | 内部/API 路径 | 中 |
| `AI经营分析报告/正式系统/交付件/adminServer.ts` | Bearer 认证说明或代码 | 高 |
| `AI经营分析报告/正式系统/交付件/adminServer.ts` | HTTP(S) 域名或端点 | 中 |
| `AI经营分析报告/正式系统/交付件/adminServer.ts` | IP 地址 | 高 |
| `AI经营分析报告/正式系统/交付件/adminServer.ts` | 内部/API 路径 | 中 |
| `AI经营分析报告/正式系统/交付件/aiBusinessRoutes.ts` | IP 地址 | 高 |
| `AI经营分析报告/正式系统/交付件/aiBusinessRoutes.ts` | 基础设施配置字段 | 中 |
| `AI经营分析报告/正式系统/交付件/checkMonthlyPlanReminder.ts` | IP 地址 | 高 |
| `AI经营分析报告/正式系统/交付件/checkMonthlyPlanReminder.ts` | 基础设施配置字段 | 中 |
| `AI经营分析报告/正式系统/交付件/checkOpsInactionAlert.ts` | IP 地址 | 高 |
| `AI经营分析报告/正式系统/交付件/checkOpsInactionAlert.ts` | 基础设施配置字段 | 中 |
| `AI经营分析报告/正式系统/交付件/feishuCardCallbackRoutes.ts` | IP 地址 | 高 |
| `AI经营分析报告/正式系统/交付件/feishuCardCallbackRoutes.ts` | 基础设施配置字段 | 中 |
| `AI经营分析报告/正式系统/交付件/generate_weekly_report.py` | IP 地址 | 高 |
| `AI经营分析报告/正式系统/交付件/generate_weekly_report.py` | 基础设施配置字段 | 中 |
| `AI经营分析报告/正式系统/交付件/sendBusinessReportNotify.ts` | IP 地址 | 高 |
| `AI经营分析报告/正式系统/交付件/sendBusinessReportNotify.ts` | 基础设施配置字段 | 中 |
| `AI经营分析报告/正式系统/交付件/sendWeeklyReportConfirmCard.ts` | Bearer 认证说明或代码 | 高 |
| `AI经营分析报告/正式系统/交付件/sendWeeklyReportConfirmCard.ts` | HTTP(S) 域名或端点 | 中 |
| `AI经营分析报告/正式系统/交付件/syncWalmartListingPrice.ts` | IP 地址 | 高 |
| `AI经营分析报告/正式系统/交付件/syncWalmartListingPrice.ts` | 基础设施配置字段 | 中 |
| `AI经营分析报告/正式系统/部署交接包.md` | IP 地址 | 高 |
| `README.md` | IP 地址 | 高 |
| `_ai_patches/patch11_adminServer_mount.py` | 内部/API 路径 | 中 |
| `_ai_patches/patch2_AppShell_ads_iframe.py` | HTTP(S) 域名或端点 | 中 |
| `_ai_patches/patch2_AppShell_ads_iframe.py` | IP 地址 | 高 |
| `_ai_patches/patch2_App_dispatch.py` | HTTP(S) 域名或端点 | 中 |
| `_ai_patches/patch2_App_dispatch.py` | IP 地址 | 高 |
| `_ai_patches/patch3_App_meeting_native.py` | HTTP(S) 域名或端点 | 中 |
| `_ai_patches/patch3_App_meeting_native.py` | IP 地址 | 高 |
| `_ai_patches/patch4_AppShell_ads_merge.py` | HTTP(S) 域名或端点 | 中 |
| `_ai_patches/patch4_AppShell_ads_merge.py` | IP 地址 | 高 |
| `_ai_patches/patch5_HelpCenter_adsfix.py` | HTTP(S) 域名或端点 | 中 |
| `_ai_patches/patch5_HelpCenter_adsfix.py` | IP 地址 | 高 |
| `_ai_patches/patch6_AppShell_adsimport.py` | HTTP(S) 域名或端点 | 中 |
| `_ai_patches/patch6_AppShell_adsimport.py` | IP 地址 | 高 |
| `_ai_patches/patch6_App_adsimport.py` | HTTP(S) 域名或端点 | 中 |
| `_ai_patches/patch6_App_adsimport.py` | IP 地址 | 高 |
| `_ai_patches/patch7_revert_adsimport.py` | HTTP(S) 域名或端点 | 中 |
| `_ai_patches/patch7_revert_adsimport.py` | IP 地址 | 高 |
| `_ai_patches/patch8_AppShell_ads4.py` | HTTP(S) 域名或端点 | 中 |
| `_ai_patches/patch8_AppShell_ads4.py` | IP 地址 | 高 |
| `_ai_patches/patch8_App_adsurl.py` | HTTP(S) 域名或端点 | 中 |
| `_ai_patches/patch8_App_adsurl.py` | IP 地址 | 高 |
| `_ai_patches/patch9_AppShell_upload.py` | HTTP(S) 域名或端点 | 中 |
| `_ai_patches/patch9_AppShell_upload.py` | IP 地址 | 高 |
| `_ai_patches/patch_App_jieqiao.py` | HTTP(S) 域名或端点 | 中 |
| `_ai_patches/patch_App_jieqiao.py` | IP 地址 | 高 |
| `admin-frontend/package-lock.json` | HTTP(S) 域名或端点 | 中 |
| `admin-frontend/public/login.html` | 内部/API 路径 | 中 |
| `admin-frontend/src/AiFinanceCredits.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/AiFinanceItemCashProfit.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/AiFinanceItemCashProfitV2.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/AiFinanceTools.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/ApiDocPage.tsx` | Bearer 认证说明或代码 | 高 |
| `admin-frontend/src/ApiDocPage.tsx` | HTTP(S) 域名或端点 | 中 |
| `admin-frontend/src/ApiDocPage.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/App.tsx` | HTTP(S) 域名或端点 | 中 |
| `admin-frontend/src/App.tsx` | IP 地址 | 高 |
| `admin-frontend/src/App.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/AppShell.tsx` | HTTP(S) 域名或端点 | 中 |
| `admin-frontend/src/AppShell.tsx` | IP 地址 | 高 |
| `admin-frontend/src/AppShell.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/Attendance.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/BusinessAnalysis.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/ClearanceCenter.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/FeishuRawSalesData.tsx` | HTTP(S) 域名或端点 | 中 |
| `admin-frontend/src/FeishuRawSalesData.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/HelpCenter.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/HrPerformance.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/ItemIdLink.tsx` | HTTP(S) 域名或端点 | 中 |
| `admin-frontend/src/LingxingSalesData.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/MeetingAnalysis.tsx` | IP 地址 | 高 |
| `admin-frontend/src/MonthlyPlanPanel.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/PmcWfsFeeCase.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/RosterAdmin.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/SalesDashboard.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/src/SalesDetailV2.tsx` | 内部/API 路径 | 中 |
| `admin-frontend/vite.config.ts` | HTTP(S) 域名或端点 | 中 |
| `admin-frontend/vite.config.ts` | 内部/API 路径 | 中 |
| `context/API_MAP.md` | HTTP(S) 域名或端点 | 中 |
| `context/CODE_DEPLOY_SOP.md` | HTTP(S) 域名或端点 | 中 |
| `context/CODE_DEPLOY_SOP.md` | IP 地址 | 高 |
| `context/DATABASE_MAP.md` | Bearer 认证说明或代码 | 高 |
| `context/DATABASE_MAP.md` | 基础设施配置字段 | 中 |
| `context/PROJECT_CONTEXT.md` | Bearer 认证说明或代码 | 高 |
| `context/PROJECT_CONTEXT.md` | IP 地址 | 高 |
| `context/SYSTEM_MAP.md` | Bearer 认证说明或代码 | 高 |
| `context/SYSTEM_MAP.md` | HTTP(S) 域名或端点 | 中 |
| `context/SYSTEM_MAP.md` | IP 地址 | 高 |
| `context/SYSTEM_MAP.md` | 基础设施配置字段 | 中 |
| `context/TASK_CHANGE_LOG.md` | Bearer 认证说明或代码 | 高 |
| `context/TASK_CHANGE_LOG.md` | HTTP(S) 域名或端点 | 中 |
| `context/TASK_CHANGE_LOG.md` | IP 地址 | 高 |
| `context/TASK_CHANGE_LOG.md` | 内部/API 路径 | 中 |
| `context/TASK_CHANGE_LOG.md` | 基础设施配置字段 | 中 |
| `context/UI_STANDARDS.md` | HTTP(S) 域名或端点 | 中 |
| `context/UI_STANDARDS.md` | IP 地址 | 高 |
| `data/api_doc_spec.json` | Bearer 认证说明或代码 | 高 |
| `data/api_doc_spec.json` | HTTP(S) 域名或端点 | 中 |
| `data/api_doc_spec.json` | IP 地址 | 高 |
| `data/api_doc_spec.json` | 内部/API 路径 | 中 |
| `docs/feishu_item_owner_sync.md` | HTTP(S) 域名或端点 | 中 |
| `docs/feishu_item_owner_sync.md` | IP 地址 | 高 |
| `docs/internal_api_readonly.md` | Bearer 认证说明或代码 | 高 |
| `docs/internal_api_readonly.md` | HTTP(S) 域名或端点 | 中 |
| `docs/internal_api_readonly.md` | IP 地址 | 高 |
| `docs/lingxing-api.json` | HTTP(S) 域名或端点 | 中 |
| `docs/lingxing/GetToken.md` | HTTP(S) 域名或端点 | 中 |
| `docs/lingxing/MultiPlatform/Advertisement/walmart-reportAdItemSpList_17.md` | HTTP(S) 域名或端点 | 中 |
| `docs/lingxing/OrderProfitListMSKU.md` | HTTP(S) 域名或端点 | 中 |
| `docs/lingxing/PlatformStatisticsSaleStatPageListV2.md` | HTTP(S) 域名或端点 | 中 |
| `docs/lingxing/ProductDetails.md` | HTTP(S) 域名或端点 | 中 |
| `docs/lingxing/ProductLists.md` | HTTP(S) 域名或端点 | 中 |
| `docs/lingxing/QueryProductList.md` | HTTP(S) 域名或端点 | 中 |
| `docs/lingxing/WalmartQueryAdvertiserList.md` | HTTP(S) 域名或端点 | 中 |
| `docs/lingxing/batchGetProductInfo.md` | HTTP(S) 域名或端点 | 中 |
| `docs/lingxing/docs_sidebar.md` | HTTP(S) 域名或端点 | 中 |
| `docs/lingxing/newInstructions.md` | HTTP(S) 域名或端点 | 中 |
| `docs/lingxing/walmartList.md` | HTTP(S) 域名或端点 | 中 |
| `docs/lingxing_daily_to_db.md` | HTTP(S) 域名或端点 | 中 |
| `docs/lingxing_daily_to_db.md` | IP 地址 | 高 |
| `docs/lingxing_daily_to_db.md` | 基础设施配置字段 | 中 |
| `docs/销售驾驶舱_v1_部署与验收.md` | HTTP(S) 域名或端点 | 中 |
| `docs/销售驾驶舱_v1_部署与验收.md` | IP 地址 | 高 |
| `docs/销售驾驶舱_v1_阶段总结.md` | HTTP(S) 域名或端点 | 中 |
| `docs/销售驾驶舱_v1_阶段总结.md` | IP 地址 | 高 |
| `docs/销售驾驶舱_v2_部署与验收.md` | HTTP(S) 域名或端点 | 中 |
| `docs/销售驾驶舱_v2_部署与验收.md` | IP 地址 | 高 |
| `legacy_feishu_20260723/aiDailyDiagnosis.ts` | Bearer 认证说明或代码 | 高 |
| `legacy_feishu_20260723/syncFeishuItemOwnerToMysql.ts` | IP 地址 | 高 |
| `legacy_feishu_20260723/syncFeishuItemOwnerToMysql.ts` | 基础设施配置字段 | 中 |
| `package-lock.json` | HTTP(S) 域名或端点 | 中 |
| `refreshFeishuMembers.ts` | Bearer 认证说明或代码 | 高 |
| `refreshFeishuMembers.ts` | HTTP(S) 域名或端点 | 中 |
| `refreshFeishuMembers.ts` | IP 地址 | 高 |
| `refreshFeishuMembers.ts` | 基础设施配置字段 | 中 |
| `scripts/ads_attr_probe.sh` | IP 地址 | 高 |
| `scripts/ads_attr_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/ambiguous_resolve_probe.sh` | IP 地址 | 高 |
| `scripts/ambiguous_resolve_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/batch13_icp_trial_probe.sh` | IP 地址 | 高 |
| `scripts/batch13_icp_trial_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/batch13_newitem_probe.sh` | IP 地址 | 高 |
| `scripts/batch13_newitem_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/deploy-server.md` | HTTP(S) 域名或端点 | 中 |
| `scripts/deploy_12bc.sh` | HTTP(S) 域名或端点 | 中 |
| `scripts/deploy_12bc.sh` | IP 地址 | 高 |
| `scripts/deploy_12bc.sh` | 基础设施配置字段 | 中 |
| `scripts/generate_monthly_report.py` | IP 地址 | 高 |
| `scripts/generate_monthly_report.py` | 基础设施配置字段 | 中 |
| `scripts/help_center_probe.sh` | IP 地址 | 高 |
| `scripts/help_center_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/help_probe_v2.sh` | IP 地址 | 高 |
| `scripts/help_probe_v2.sh` | 基础设施配置字段 | 中 |
| `scripts/icp_audit_probe3.sh` | IP 地址 | 高 |
| `scripts/icp_audit_probe3.sh` | 基础设施配置字段 | 中 |
| `scripts/icp_audit_probe4.sh` | IP 地址 | 高 |
| `scripts/icp_audit_probe4.sh` | 基础设施配置字段 | 中 |
| `scripts/icp_clean_newitem_probe.sh` | IP 地址 | 高 |
| `scripts/icp_clean_newitem_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/icp_full_audit_probe.sh` | IP 地址 | 高 |
| `scripts/icp_full_audit_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/icp_itemid_probe.sh` | IP 地址 | 高 |
| `scripts/icp_itemid_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/icp_itemid_probe2.sh` | IP 地址 | 高 |
| `scripts/icp_itemid_probe2.sh` | 基础设施配置字段 | 中 |
| `scripts/inbound_missing_audit.sh` | IP 地址 | 高 |
| `scripts/inbound_missing_audit.sh` | 基础设施配置字段 | 中 |
| `scripts/inbound_reimport_audit.sh` | IP 地址 | 高 |
| `scripts/inbound_reimport_audit.sh` | 基础设施配置字段 | 中 |
| `scripts/inspect_mysql_schema.ts` | 基础设施配置字段 | 中 |
| `scripts/itemid_probe.sh` | IP 地址 | 高 |
| `scripts/itemid_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/msku_backfill.sh` | IP 地址 | 高 |
| `scripts/msku_backfill.sh` | 基础设施配置字段 | 中 |
| `scripts/msku_backfill_v2.sh` | IP 地址 | 高 |
| `scripts/msku_backfill_v2.sh` | 基础设施配置字段 | 中 |
| `scripts/msku_blank_probe.sh` | IP 地址 | 高 |
| `scripts/msku_blank_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/msku_dedupe_fix.sh` | IP 地址 | 高 |
| `scripts/msku_dedupe_fix.sh` | 基础设施配置字段 | 中 |
| `scripts/rebuild_auto_ads_fact.py` | IP 地址 | 高 |
| `scripts/rebuild_auto_ads_fact.py` | 基础设施配置字段 | 中 |
| `scripts/recon_sem_probe.sh` | IP 地址 | 高 |
| `scripts/recon_sem_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/sem_billing_probe.sh` | IP 地址 | 高 |
| `scripts/sem_billing_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/sem_dedup_probe.sh` | IP 地址 | 高 |
| `scripts/sem_dedup_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/sem_manual_attr.sh` | IP 地址 | 高 |
| `scripts/sem_manual_attr.sh` | 基础设施配置字段 | 中 |
| `scripts/sem_map_probe.sh` | IP 地址 | 高 |
| `scripts/sem_map_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/sem_map_propagate.sh` | IP 地址 | 高 |
| `scripts/sem_map_propagate.sh` | 基础设施配置字段 | 中 |
| `scripts/sem_probe.sh` | IP 地址 | 高 |
| `scripts/sem_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/sem_sentinel_diag.sh` | IP 地址 | 高 |
| `scripts/sem_sentinel_diag.sh` | 基础设施配置字段 | 中 |
| `scripts/sem_unmatched_dump.sh` | IP 地址 | 高 |
| `scripts/sem_unmatched_dump.sh` | 基础设施配置字段 | 中 |
| `scripts/ship_purchase_gap_probe.sh` | IP 地址 | 高 |
| `scripts/ship_purchase_gap_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/sku_split_probe.sh` | IP 地址 | 高 |
| `scripts/sku_split_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/storage_dup_commission_probe.sh` | IP 地址 | 高 |
| `scripts/storage_dup_commission_probe.sh` | 基础设施配置字段 | 中 |
| `scripts/storage_gap_audit.sh` | IP 地址 | 高 |
| `scripts/storage_gap_audit.sh` | 基础设施配置字段 | 中 |
| `scripts/storage_overlap_fix.sh` | IP 地址 | 高 |
| `scripts/storage_overlap_fix.sh` | 基础设施配置字段 | 中 |
| `scripts/updateProductManagementStatus.ts` | IP 地址 | 高 |
| `scripts/updateProductManagementStatus.ts` | 基础设施配置字段 | 中 |
| `scripts/verify_report_and_noorder_migration.sh` | IP 地址 | 高 |
| `scripts/verify_report_and_noorder_migration.sh` | 基础设施配置字段 | 中 |
| `src/adminServer.ts` | Bearer 认证说明或代码 | 高 |
| `src/adminServer.ts` | HTTP(S) 域名或端点 | 中 |
| `src/adminServer.ts` | IP 地址 | 高 |
| `src/adminServer.ts` | 内部/API 路径 | 中 |
| `src/adsFeeReportRoutes.ts` | IP 地址 | 高 |
| `src/adsFeeReportRoutes.ts` | 基础设施配置字段 | 中 |
| `src/aiBusinessRoutes.ts` | IP 地址 | 高 |
| `src/aiBusinessRoutes.ts` | 基础设施配置字段 | 中 |
| `src/aiFinanceIcpV2Routes.ts` | IP 地址 | 高 |
| `src/aiFinanceIcpV2Routes.ts` | 基础设施配置字段 | 中 |
| `src/aiFinanceRoutes.ts` | IP 地址 | 高 |
| `src/aiFinanceRoutes.ts` | 基础设施配置字段 | 中 |
| `src/aiOpsLogReview.ts` | Bearer 认证说明或代码 | 高 |
| `src/aiOpsLogReview.ts` | IP 地址 | 高 |
| `src/aiOpsLogReview.ts` | 基础设施配置字段 | 中 |
| `src/ai_pmc/aiEvaluate.ts` | Bearer 认证说明或代码 | 高 |
| `src/ai_pmc/readOwners.ts` | IP 地址 | 高 |
| `src/ai_pmc/readOwners.ts` | 基础设施配置字段 | 中 |
| `src/apiKeyManager.ts` | Bearer 认证说明或代码 | 高 |
| `src/apiKeyManager.ts` | HTTP(S) 域名或端点 | 中 |
| `src/apiKeyManager.ts` | IP 地址 | 高 |
| `src/apiKeyManager.ts` | 内部/API 路径 | 中 |
| `src/apiKeyManager.ts` | 基础设施配置字段 | 中 |
| `src/archiveCsProductsBatch.ts` | IP 地址 | 高 |
| `src/archiveCsProductsBatch.ts` | 基础设施配置字段 | 中 |
| `src/arrivalNotify.ts` | IP 地址 | 高 |
| `src/arrivalNotify.ts` | 基础设施配置字段 | 中 |
| `src/attendanceLackAlert.ts` | HTTP(S) 域名或端点 | 中 |
| `src/attendanceLackAlert.ts` | IP 地址 | 高 |
| `src/attendanceLackAlert.ts` | 基础设施配置字段 | 中 |
| `src/attendanceRoutes.ts` | IP 地址 | 高 |
| `src/attendanceRoutes.ts` | 基础设施配置字段 | 中 |
| `src/authService.ts` | IP 地址 | 高 |
| `src/authService.ts` | 基础设施配置字段 | 中 |
| `src/checkArchivedRestockAlert.ts` | IP 地址 | 高 |
| `src/checkArchivedRestockAlert.ts` | 基础设施配置字段 | 中 |
| `src/checkAutoAdSearchTermImport.ts` | HTTP(S) 域名或端点 | 中 |
| `src/checkAutoAdSearchTermImport.ts` | IP 地址 | 高 |
| `src/checkAutoAdSearchTermImport.ts` | 基础设施配置字段 | 中 |
| `src/checkClearanceNoTargetAlert.ts` | IP 地址 | 高 |
| `src/checkClearanceNoTargetAlert.ts` | 基础设施配置字段 | 中 |
| `src/checkCostConfigMissing.ts` | IP 地址 | 高 |
| `src/checkCostConfigMissing.ts` | 基础设施配置字段 | 中 |
| `src/checkMonthlyPlanDeduction.ts` | IP 地址 | 高 |
| `src/checkMonthlyPlanDeduction.ts` | 基础设施配置字段 | 中 |
| `src/checkMonthlyPlanReminder.ts` | IP 地址 | 高 |
| `src/checkMonthlyPlanReminder.ts` | 基础设施配置字段 | 中 |
| `src/checkOnsiteAdsInvoiceSentinel.ts` | HTTP(S) 域名或端点 | 中 |
| `src/checkOnsiteAdsInvoiceSentinel.ts` | IP 地址 | 高 |
| `src/checkOnsiteAdsInvoiceSentinel.ts` | 基础设施配置字段 | 中 |
| `src/checkOpsInactionAlert.ts` | IP 地址 | 高 |
| `src/checkOpsInactionAlert.ts` | 基础设施配置字段 | 中 |
| `src/checkOrderDrop.ts` | IP 地址 | 高 |
| `src/checkOrderDrop.ts` | 基础设施配置字段 | 中 |
| `src/checkSemImport.ts` | HTTP(S) 域名或端点 | 中 |
| `src/checkSemImport.ts` | IP 地址 | 高 |
| `src/checkSemImport.ts` | 基础设施配置字段 | 中 |
| `src/checkSemNamingCompliance.ts` | HTTP(S) 域名或端点 | 中 |
| `src/checkSemNamingCompliance.ts` | IP 地址 | 高 |
| `src/checkSemNamingCompliance.ts` | 基础设施配置字段 | 中 |
| `src/checkSemNamingDeduction.ts` | HTTP(S) 域名或端点 | 中 |
| `src/checkSemNamingDeduction.ts` | IP 地址 | 高 |
| `src/checkSemNamingDeduction.ts` | 基础设施配置字段 | 中 |
| `src/checkWfsFeeAnomaly.ts` | IP 地址 | 高 |
| `src/checkWfsFeeAnomaly.ts` | 基础设施配置字段 | 中 |
| `src/clearDepartedOwners.ts` | IP 地址 | 高 |
| `src/clearDepartedOwners.ts` | 基础设施配置字段 | 中 |
| `src/clearanceApprovalNotify.ts` | IP 地址 | 高 |
| `src/clearanceApprovalNotify.ts` | 基础设施配置字段 | 中 |
| `src/clearanceCardsNotify.ts` | IP 地址 | 高 |
| `src/clearanceCardsNotify.ts` | 基础设施配置字段 | 中 |
| `src/clearanceCenterRoutes.ts` | HTTP(S) 域名或端点 | 中 |
| `src/clearanceCenterRoutes.ts` | IP 地址 | 高 |
| `src/clearanceCenterRoutes.ts` | 基础设施配置字段 | 中 |
| `src/csTestAlertNotify.ts` | IP 地址 | 高 |
| `src/csTestAlertNotify.ts` | 基础设施配置字段 | 中 |
| `src/deriveLaunchDate.ts` | IP 地址 | 高 |
| `src/deriveLaunchDate.ts` | 基础设施配置字段 | 中 |
| `src/expandStorageFeeDaily.ts` | IP 地址 | 高 |
| `src/expandStorageFeeDaily.ts` | 基础设施配置字段 | 中 |
| `src/feishuCardCallbackRoutes.ts` | HTTP(S) 域名或端点 | 中 |
| `src/feishuCardCallbackRoutes.ts` | IP 地址 | 高 |
| `src/feishuCardCallbackRoutes.ts` | 基础设施配置字段 | 中 |
| `src/feishuNotify.ts` | Bearer 认证说明或代码 | 高 |
| `src/feishuNotify.ts` | HTTP(S) 域名或端点 | 中 |
| `src/feishuNotify.ts` | IP 地址 | 高 |
| `src/feishuNotify.ts` | 基础设施配置字段 | 中 |
| `src/feishuRawSalesRoutes.ts` | IP 地址 | 高 |
| `src/feishuRawSalesRoutes.ts` | 基础设施配置字段 | 中 |
| `src/gptKwOwnerSummary.ts` | HTTP(S) 域名或端点 | 中 |
| `src/gptKwOwnerSummary.ts` | IP 地址 | 高 |
| `src/gptKwOwnerSummary.ts` | 基础设施配置字段 | 中 |
| `src/helpRoutes.ts` | IP 地址 | 高 |
| `src/helpRoutes.ts` | 基础设施配置字段 | 中 |
| `src/hrRoutes.ts` | HTTP(S) 域名或端点 | 中 |
| `src/hrRoutes.ts` | IP 地址 | 高 |
| `src/hrRoutes.ts` | 基础设施配置字段 | 中 |
| `src/internalReadonlyApi.ts` | Bearer 认证说明或代码 | 高 |
| `src/internalReadonlyApi.ts` | IP 地址 | 高 |
| `src/internalReadonlyApi.ts` | 内部/API 路径 | 中 |
| `src/internalReadonlyApi.ts` | 基础设施配置字段 | 中 |
| `src/lingxingClient.ts` | 内部/API 路径 | 中 |
| `src/lingxingSalesRoutes.ts` | IP 地址 | 高 |
| `src/lingxingSalesRoutes.ts` | 内部/API 路径 | 中 |
| `src/lingxingSalesRoutes.ts` | 基础设施配置字段 | 中 |
| `src/lowProfitNotify.ts` | IP 地址 | 高 |
| `src/lowProfitNotify.ts` | 基础设施配置字段 | 中 |
| `src/meetingAnalysis.ts` | Bearer 认证说明或代码 | 高 |
| `src/meetingServer.ts` | Bearer 认证说明或代码 | 高 |
| `src/meetingServer.ts` | HTTP(S) 域名或端点 | 中 |
| `src/meetingServer.ts` | 内部/API 路径 | 中 |
| `src/noOrderNotify.ts` | IP 地址 | 高 |
| `src/noOrderNotify.ts` | 基础设施配置字段 | 中 |
| `src/notifyRules/reminderCards.test.ts` | HTTP(S) 域名或端点 | 中 |
| `src/orderDropNotify.ts` | IP 地址 | 高 |
| `src/orderDropNotify.ts` | 基础设施配置字段 | 中 |
| `src/orderProfitV2Routes.ts` | IP 地址 | 高 |
| `src/orderProfitV2Routes.ts` | 基础设施配置字段 | 中 |
| `src/performanceSummaryReport.ts` | IP 地址 | 高 |
| `src/performanceSummaryReport.ts` | 基础设施配置字段 | 中 |
| `src/pmcFeeDetailRoutes.ts` | IP 地址 | 高 |
| `src/pmcFeeDetailRoutes.ts` | 基础设施配置字段 | 中 |
| `src/pmcInventoryRoutes.ts` | IP 地址 | 高 |
| `src/pmcInventoryRoutes.ts` | 基础设施配置字段 | 中 |
| `src/pmcRoutes.ts` | IP 地址 | 高 |
| `src/pmcRoutes.ts` | 基础设施配置字段 | 中 |
| `src/pmcWfsFeeRoutes.ts` | IP 地址 | 高 |
| `src/pmcWfsFeeRoutes.ts` | 基础设施配置字段 | 中 |
| `src/probeAdCampaignLevelReconcile.ts` | IP 地址 | 高 |
| `src/probeAdCampaignLevelReconcile.ts` | 基础设施配置字段 | 中 |
| `src/probeAdCampaignTypeEnum.ts` | IP 地址 | 高 |
| `src/probeAdCampaignTypeEnum.ts` | 基础设施配置字段 | 中 |
| `src/probeAdFeeMskuReconcile.ts` | IP 地址 | 高 |
| `src/probeAdFeeMskuReconcile.ts` | 基础设施配置字段 | 中 |
| `src/probeAdGroupAndBidMultiplier.ts` | IP 地址 | 高 |
| `src/probeAdGroupAndBidMultiplier.ts` | 基础设施配置字段 | 中 |
| `src/probeAdItemLevelSpendCheck.ts` | IP 地址 | 高 |
| `src/probeAdItemLevelSpendCheck.ts` | 基础设施配置字段 | 中 |
| `src/probeAdLiveVsInvoiceCompare.ts` | IP 地址 | 高 |
| `src/probeAdLiveVsInvoiceCompare.ts` | 基础设施配置字段 | 中 |
| `src/probeAdsBidBudgetStrategy.ts` | IP 地址 | 高 |
| `src/probeAdsBidBudgetStrategy.ts` | 基础设施配置字段 | 中 |
| `src/probeAdsNewDimensions.ts` | IP 地址 | 高 |
| `src/probeAdsNewDimensions.ts` | 基础设施配置字段 | 中 |
| `src/probeAutoAdCsvVsApiReconcile.ts` | IP 地址 | 高 |
| `src/probeAutoAdCsvVsApiReconcile.ts` | 基础设施配置字段 | 中 |
| `src/probeAutoCsvCoverageAndRatio.ts` | IP 地址 | 高 |
| `src/probeAutoCsvCoverageAndRatio.ts` | 基础设施配置字段 | 中 |
| `src/probeCommissionSaving.ts` | IP 地址 | 高 |
| `src/probeCommissionSaving.ts` | 基础设施配置字段 | 中 |
| `src/probeFactAdsProductDailyAudit.ts` | IP 地址 | 高 |
| `src/probeFactAdsProductDailyAudit.ts` | 基础设施配置字段 | 中 |
| `src/probeInTransitOverlap.ts` | IP 地址 | 高 |
| `src/probeInTransitOverlap.ts` | 基础设施配置字段 | 中 |
| `src/probeInventoryOverview.ts` | IP 地址 | 高 |
| `src/probeInventoryOverview.ts` | 基础设施配置字段 | 中 |
| `src/probePriceOscillationAndRepricing.ts` | IP 地址 | 高 |
| `src/probePriceOscillationAndRepricing.ts` | 基础设施配置字段 | 中 |
| `src/probePriceVsOrderAvg.ts` | IP 地址 | 高 |
| `src/probePriceVsOrderAvg.ts` | 基础设施配置字段 | 中 |
| `src/probeSampleOrderAnomalyDetail.ts` | IP 地址 | 高 |
| `src/probeSampleOrderAnomalyDetail.ts` | 基础设施配置字段 | 中 |
| `src/probeSampleOrderCostLeak.ts` | IP 地址 | 高 |
| `src/probeSampleOrderCostLeak.ts` | 基础设施配置字段 | 中 |
| `src/probeSbSvAdData.ts` | IP 地址 | 高 |
| `src/probeSbSvAdData.ts` | 基础设施配置字段 | 中 |
| `src/probeSbSvAdEndpoints.ts` | IP 地址 | 高 |
| `src/probeSbSvAdEndpoints.ts` | 基础设施配置字段 | 中 |
| `src/probeSbSvParamIsolate.ts` | IP 地址 | 高 |
| `src/probeSbSvParamIsolate.ts` | 基础设施配置字段 | 中 |
| `src/probeSemCreditReconcile.ts` | IP 地址 | 高 |
| `src/probeSemCreditReconcile.ts` | 基础设施配置字段 | 中 |
| `src/probeSettlementCostReliability.ts` | IP 地址 | 高 |
| `src/probeSettlementCostReliability.ts` | 基础设施配置字段 | 中 |
| `src/probeSettlementDateDistribution.ts` | IP 地址 | 高 |
| `src/probeSettlementDateDistribution.ts` | 基础设施配置字段 | 中 |
| `src/probeSettlementLagAndStorageFee.ts` | IP 地址 | 高 |
| `src/probeSettlementLagAndStorageFee.ts` | 基础设施配置字段 | 中 |
| `src/probeSettlementRefund.ts` | IP 地址 | 高 |
| `src/probeSettlementRefund.ts` | 基础设施配置字段 | 中 |
| `src/probeSpKeywordStatus.ts` | IP 地址 | 高 |
| `src/probeSpKeywordStatus.ts` | 基础设施配置字段 | 中 |
| `src/probeStatementBoundary.ts` | IP 地址 | 高 |
| `src/probeStatementBoundary.ts` | 基础设施配置字段 | 中 |
| `src/probeStatementFullPull.ts` | IP 地址 | 高 |
| `src/probeStatementFullPull.ts` | 基础设施配置字段 | 中 |
| `src/probeStatementGapForensics.ts` | IP 地址 | 高 |
| `src/probeStatementGapForensics.ts` | 基础设施配置字段 | 中 |
| `src/probeStatementPagination.ts` | IP 地址 | 高 |
| `src/probeStatementPagination.ts` | 基础设施配置字段 | 中 |
| `src/probeStatementTypeGap.ts` | IP 地址 | 高 |
| `src/probeStatementTypeGap.ts` | 基础设施配置字段 | 中 |
| `src/probeStatementWindow.ts` | IP 地址 | 高 |
| `src/probeStatementWindow.ts` | 基础设施配置字段 | 中 |
| `src/probeStoreSettlementReconcile.ts` | IP 地址 | 高 |
| `src/probeStoreSettlementReconcile.ts` | 基础设施配置字段 | 中 |
| `src/probeT1AndOrderPrice.ts` | IP 地址 | 高 |
| `src/probeT1AndOrderPrice.ts` | 基础设施配置字段 | 中 |
| `src/probeWalmartBillApis.ts` | IP 地址 | 高 |
| `src/probeWalmartBillApis.ts` | 基础设施配置字段 | 中 |
| `src/productRuleSignalNotify.ts` | HTTP(S) 域名或端点 | 中 |
| `src/productRuleSignalNotify.ts` | IP 地址 | 高 |
| `src/productRuleSignalNotify.ts` | 基础设施配置字段 | 中 |
| `src/refreshFeishuMembers.ts` | Bearer 认证说明或代码 | 高 |
| `src/refreshFeishuMembers.ts` | HTTP(S) 域名或端点 | 中 |
| `src/refreshFeishuMembers.ts` | IP 地址 | 高 |
| `src/refreshFeishuMembers.ts` | 基础设施配置字段 | 中 |
| `src/refreshGroupRoster.ts` | Bearer 认证说明或代码 | 高 |
| `src/refreshGroupRoster.ts` | HTTP(S) 域名或端点 | 中 |
| `src/repairBlankMskuRows.ts` | IP 地址 | 高 |
| `src/repairBlankMskuRows.ts` | 基础设施配置字段 | 中 |
| `src/repairV2TimezoneAndStore.ts` | IP 地址 | 高 |
| `src/repairV2TimezoneAndStore.ts` | 基础设施配置字段 | 中 |
| `src/replayManualAdKeywordFromRaw.ts` | IP 地址 | 高 |
| `src/replayManualAdKeywordFromRaw.ts` | 基础设施配置字段 | 中 |
| `src/reportV2Reconcile.ts` | IP 地址 | 高 |
| `src/reportV2Reconcile.ts` | 基础设施配置字段 | 中 |
| `src/salesDetailV2Routes.ts` | IP 地址 | 高 |
| `src/salesDetailV2Routes.ts` | 基础设施配置字段 | 中 |
| `src/sendBusinessReportNotify.ts` | IP 地址 | 高 |
| `src/sendBusinessReportNotify.ts` | 基础设施配置字段 | 中 |
| `src/sendWeeklyReportConfirmCard.ts` | Bearer 认证说明或代码 | 高 |
| `src/sendWeeklyReportConfirmCard.ts` | HTTP(S) 域名或端点 | 中 |
| `src/sentinelCore.ts` | IP 地址 | 高 |
| `src/sentinelCore.ts` | 基础设施配置字段 | 中 |
| `src/services/lingxingDailyMetricsService.ts` | IP 地址 | 高 |
| `src/services/lingxingDailyMetricsService.ts` | 基础设施配置字段 | 中 |
| `src/services/salesDashboardService.ts` | IP 地址 | 高 |
| `src/services/salesDashboardService.ts` | 基础设施配置字段 | 中 |
| `src/storeRegistry.ts` | IP 地址 | 高 |
| `src/storeRegistry.ts` | 基础设施配置字段 | 中 |
| `src/syncAdsConfigSnapshotDaily.ts` | IP 地址 | 高 |
| `src/syncAdsConfigSnapshotDaily.ts` | 基础设施配置字段 | 中 |
| `src/syncFeishuAttendance.ts` | Bearer 认证说明或代码 | 高 |
| `src/syncFeishuAttendance.ts` | HTTP(S) 域名或端点 | 中 |
| `src/syncFeishuAttendance.ts` | IP 地址 | 高 |
| `src/syncFeishuAttendance.ts` | 基础设施配置字段 | 中 |
| `src/syncLingxingBatch.ts` | IP 地址 | 高 |
| `src/syncLingxingBatch.ts` | 基础设施配置字段 | 中 |
| `src/syncLingxingDailyToDb.ts` | IP 地址 | 高 |
| `src/syncLingxingDailyToDb.ts` | 基础设施配置字段 | 中 |
| `src/syncLingxingFxRate.ts` | IP 地址 | 高 |
| `src/syncLingxingFxRate.ts` | 基础设施配置字段 | 中 |
| `src/syncLingxingProductCost.ts` | IP 地址 | 高 |
| `src/syncLingxingProductCost.ts` | 基础设施配置字段 | 中 |
| `src/syncLingxingToRawFeishu.ts` | IP 地址 | 高 |
| `src/syncLingxingToRawFeishu.ts` | 基础设施配置字段 | 中 |
| `src/syncLocalInventory.ts` | IP 地址 | 高 |
| `src/syncLocalInventory.ts` | 基础设施配置字段 | 中 |
| `src/syncManualAdKeywordDaily.ts` | IP 地址 | 高 |
| `src/syncManualAdKeywordDaily.ts` | 基础设施配置字段 | 中 |
| `src/syncMpOrderDiscount.ts` | IP 地址 | 高 |
| `src/syncMpOrderDiscount.ts` | 基础设施配置字段 | 中 |
| `src/syncMpOrdersChannelDaily.ts` | IP 地址 | 高 |
| `src/syncMpOrdersChannelDaily.ts` | 基础设施配置字段 | 中 |
| `src/syncOrderProfitDaily.ts` | IP 地址 | 高 |
| `src/syncOrderProfitDaily.ts` | 基础设施配置字段 | 中 |
| `src/syncProductCostToMysql.ts` | IP 地址 | 高 |
| `src/syncProductCostToMysql.ts` | 基础设施配置字段 | 中 |
| `src/syncProductNameFromLingxing.ts` | IP 地址 | 高 |
| `src/syncProductNameFromLingxing.ts` | 基础设施配置字段 | 中 |
| `src/syncPurchaseCash.ts` | IP 地址 | 高 |
| `src/syncPurchaseCash.ts` | 基础设施配置字段 | 中 |
| `src/syncPurchaseOrders.ts` | IP 地址 | 高 |
| `src/syncPurchaseOrders.ts` | 基础设施配置字段 | 中 |
| `src/syncSbSvAdsDaily.ts` | IP 地址 | 高 |
| `src/syncSbSvAdsDaily.ts` | 基础设施配置字段 | 中 |
| `src/syncSettlementMonthly.ts` | IP 地址 | 高 |
| `src/syncSettlementMonthly.ts` | 基础设施配置字段 | 中 |
| `src/syncShippingOrders.ts` | IP 地址 | 高 |
| `src/syncShippingOrders.ts` | 基础设施配置字段 | 中 |
| `src/syncTemuClearanceListing.ts` | IP 地址 | 高 |
| `src/syncTemuClearanceListing.ts` | 基础设施配置字段 | 中 |
| `src/syncWalmartBillDaily.ts` | IP 地址 | 高 |
| `src/syncWalmartBillDaily.ts` | 基础设施配置字段 | 中 |
| `src/syncWalmartListingPrice.ts` | IP 地址 | 高 |
| `src/syncWalmartListingPrice.ts` | 基础设施配置字段 | 中 |
| `src/syncWalmartReturnOrders.ts` | IP 地址 | 高 |
| `src/syncWalmartReturnOrders.ts` | 基础设施配置字段 | 中 |
| `src/syncWalmartStores.ts` | IP 地址 | 高 |
| `src/syncWalmartStores.ts` | 基础设施配置字段 | 中 |
| `src/syncWfsFeeFromSettlement.ts` | IP 地址 | 高 |
| `src/syncWfsFeeFromSettlement.ts` | 基础设施配置字段 | 中 |
| `src/syncWfsShipments.ts` | IP 地址 | 高 |
| `src/syncWfsShipments.ts` | 基础设施配置字段 | 中 |
| `src/unmatchedOwnerNotify.ts` | HTTP(S) 域名或端点 | 中 |
| `src/unmatchedOwnerNotify.ts` | IP 地址 | 高 |
| `src/unmatchedOwnerNotify.ts` | 基础设施配置字段 | 中 |
| `交付件/HrPerformance.tsx` | 内部/API 路径 | 中 |
| `交付件/aiOpsLogReview.ts` | Bearer 认证说明或代码 | 高 |
| `交付件/aiOpsLogReview.ts` | IP 地址 | 高 |
| `交付件/aiOpsLogReview.ts` | 基础设施配置字段 | 中 |
| `交付件/checkAutoAdSearchTermImport_v3_db.ts` | HTTP(S) 域名或端点 | 中 |
| `交付件/checkAutoAdSearchTermImport_v3_db.ts` | IP 地址 | 高 |
| `交付件/checkAutoAdSearchTermImport_v3_db.ts` | 基础设施配置字段 | 中 |
| `交付件/csTestAlertNotify.ts` | IP 地址 | 高 |
| `交付件/csTestAlertNotify.ts` | 基础设施配置字段 | 中 |
| `交付件/hrRoutes.ts` | IP 地址 | 高 |
| `交付件/hrRoutes.ts` | 基础设施配置字段 | 中 |
| `交付件/internal_readonly_api_接口文档_20260727.md` | Bearer 认证说明或代码 | 高 |
| `交付件/internal_readonly_api_接口文档_20260727.md` | HTTP(S) 域名或端点 | 中 |
| `交付件/internal_readonly_api_接口文档_20260727.md` | IP 地址 | 高 |
| `交付件/patch_CS预警原因列_routes.py` | IP 地址 | 高 |
| `交付件/patch_CS预警原因列_前端.py` | 内部/API 路径 | 中 |
| `交付件/patch_GPT链接_前端.py` | HTTP(S) 域名或端点 | 中 |
| `交付件/patch_GPT链接_前端.py` | 内部/API 路径 | 中 |
| `交付件/patch_hr挂载与路由.py` | 内部/API 路径 | 中 |
| `交付件/patch_取消CS规则面板_前端.py` | 内部/API 路径 | 中 |
| `交付件/patch_月度规划批量导入_前端.py` | 内部/API 路径 | 中 |
| `交付件/patch_月度规划模板xlsx_前端v3.py` | 内部/API 路径 | 中 |
| `交付件/patch_清货审批入口_前端.py` | 内部/API 路径 | 中 |
| `交付件/patch_清货导入负责人_前端.py` | 内部/API 路径 | 中 |
| `交付件/patch_清货目标产品维度_前端.py` | 内部/API 路径 | 中 |
| `交付件/syncMpOrdersChannelDaily.ts` | IP 地址 | 高 |
| `交付件/syncMpOrdersChannelDaily.ts` | 基础设施配置字段 | 中 |
| `交付件/syncMpOrdersChannelDaily.扩渠道.ts` | IP 地址 | 高 |
| `交付件/syncMpOrdersChannelDaily.扩渠道.ts` | 基础设施配置字段 | 中 |
| `交付件/syncMpOrdersChannelDaily.按ASIN.ts` | IP 地址 | 高 |
| `交付件/syncMpOrdersChannelDaily.按ASIN.ts` | 基础设施配置字段 | 中 |
| `交付件/unmatchedOwnerNotify_v4_perf.ts` | HTTP(S) 域名或端点 | 中 |
| `交付件/unmatchedOwnerNotify_v4_perf.ts` | IP 地址 | 高 |
| `交付件/unmatchedOwnerNotify_v4_perf.ts` | 基础设施配置字段 | 中 |
| `交付件/walmart_sbsv_delivery/frontend/walmart-sbsv-data/page.tsx` | 内部/API 路径 | 中 |
| `交付件/walmart_sem_delivery/frontend/walmart-sem-data/page.tsx` | 内部/API 路径 | 中 |
| `交付件/wfs_fee_demo_v05.html` | HTTP(S) 域名或端点 | 中 |
| `交付件/帮助文章_WFS配送费追回SOP_20260811.md` | HTTP(S) 域名或端点 | 中 |
| `交付件/帮助文章_商品ID跳转链接_20260723.md` | HTTP(S) 域名或端点 | 中 |
| `交付件/方案设计_AI智能人事系统V1_运营绩效管理.md` | HTTP(S) 域名或端点 | 中 |
| `交付件/方案设计_AI智能人事系统V1_运营绩效管理.md` | IP 地址 | 高 |
| `公司人员花名册_dim_feishu_member_说明.md` | IP 地址 | 高 |
| `月报系统/交付件/generate_monthly_report.py` | IP 地址 | 高 |
| `月报系统/交付件/generate_monthly_report.py` | 基础设施配置字段 | 中 |
| `系统BUG体检报告_v2_20260724.md` | HTTP(S) 域名或端点 | 中 |
| `系统BUG体检报告_v2_20260724.md` | IP 地址 | 高 |
| `项目交接报告_2026-07-08.md` | HTTP(S) 域名或端点 | 中 |
| `项目交接报告_2026-07-08.md` | IP 地址 | 高 |
| `项目总结_GPT经营分析系统_2026-07.md` | Bearer 认证说明或代码 | 高 |
| `项目总结_GPT经营分析系统_2026-07.md` | HTTP(S) 域名或端点 | 中 |
| `项目总结_GPT经营分析系统_2026-07.md` | IP 地址 | 高 |

待人工复查文件数：289。

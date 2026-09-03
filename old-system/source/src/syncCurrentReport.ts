import currentReport from "../config/currentReport.json";
import { loadConfig } from "./config";
import { FeishuSheetWriter, SheetRow } from "./feishuSheetWriter";
import { LingxingClient } from "./lingxingClient";
import { TableOperationLogger } from "./tableOperationLogger";

interface MarketplaceItem {
  mid?: number;
  region?: string;
  aws_region?: string;
  country?: string;
  code?: string;
  marketplace_id?: string;
}

const TASK_NAME = "当前表格测试同步";
const TEST_SOURCE_PATH = "/erp/sc/data/seller/allMarketplace";
const TEST_TARGET_SHEET_NAME = "表格操作日志";
const TEST_DATA_RANGE = "A40:F45";

async function main(): Promise<void> {
  const startedAt = Date.now();
  const runId = createRunId();
  const confirmWrite = process.argv.includes("--confirm-write");
  const dryRun = !confirmWrite;
  const writer = new FeishuSheetWriter();
  const logger = new TableOperationLogger(writer, {
    spreadsheetToken: currentReport.spreadsheetToken,
    logSheetId: currentReport.sheets["表格操作日志"],
    dryRun,
    confirmWrite,
  });

  let fetchedCount = 0;
  let writtenCount = 0;
  let failedCount = 0;
  let status = "success";
  let errorMessage = "";

  console.log("当前飞书表格数据抓取与写入框架");
  console.log(`运行ID: ${runId}`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log("本阶段只调用领星只读接口，不写入正式当日数据。");

  try {
    const config = loadConfig();
    const client = new LingxingClient(config);
    const response = await client.request<MarketplaceItem[]>({
      method: "GET",
      path: TEST_SOURCE_PATH,
    });
    const marketplaces = response.data ?? [];
    fetchedCount = marketplaces.length;

    const previewRows = buildMarketplacePreviewRows(marketplaces.slice(0, 5));
    console.log(`领星只读接口返回条数: ${fetchedCount}`);
    console.log(`测试写入区域: ${TEST_TARGET_SHEET_NAME}!${TEST_DATA_RANGE}`);
    console.log("测试数据预览:");
    console.log(JSON.stringify(previewRows, null, 2));

    writer.writeCells({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[TEST_TARGET_SHEET_NAME],
      sheetName: TEST_TARGET_SHEET_NAME,
      range: TEST_DATA_RANGE,
      rows: previewRows,
      dryRun,
      confirmWrite,
      allowOverwrite: false,
    });

    writtenCount = confirmWrite ? previewRows.length : 0;
  } catch (error) {
    failedCount = 1;
    status = "failed";
    errorMessage = error instanceof Error ? error.message : String(error);
    console.log(`同步失败: ${errorMessage}`);
  } finally {
    const durationSeconds = Number(((Date.now() - startedAt) / 1000).toFixed(3));

    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: TEST_TARGET_SHEET_NAME,
        operationType: dryRun ? "dry-run" : "write",
        dataSource: TEST_SOURCE_PATH,
        dateRange: "N/A",
        fetchedCount,
        writtenCount,
        updatedCount: 0,
        skippedCount: dryRun ? fetchedCount : 0,
        failedCount,
        status: dryRun && status === "success" ? "dry-run" : status,
        errorMessage,
        durationSeconds,
        runId,
        environment: "local",
        remark: "第一版测试链路，不写入正式当日数据",
      });
    } catch (logError) {
      console.log(`记录操作日志失败: ${logError instanceof Error ? logError.message : String(logError)}`);
    }
  }
}

function buildMarketplacePreviewRows(items: MarketplaceItem[]): SheetRow[] {
  return [
    ["mid", "region", "aws_region", "country", "code", "marketplace_id"],
    ...items.map((item) => [
      item.mid ?? "",
      item.region ?? "",
      item.aws_region ?? "",
      item.country ?? "",
      item.code ?? "",
      item.marketplace_id ?? "",
    ]),
  ];
}

function createRunId(): string {
  return `run_${new Date().toISOString().replace(/[-:.TZ]/g, "")}_${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

main().catch((error) => {
  console.log(`执行失败: ${error instanceof Error ? error.message : String(error)}`);
});

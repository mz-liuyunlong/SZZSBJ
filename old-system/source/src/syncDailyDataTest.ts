import currentReport from "../config/currentReportFieldMapping.json";
import { loadConfig } from "./config";
import { FeishuSheetWriter, SheetRow } from "./feishuSheetWriter";
import { LingxingClient } from "./lingxingClient";
import { TableOperationLogger } from "./tableOperationLogger";

const TASK_NAME = "当日数据测试写入";
const TARGET_SHEET_NAME = "当日数据";
const LOG_SHEET_NAME = "表格操作日志";

const STORE_ID = "110687423514268160";
const STORE_NAME = "CN2601-瑞盈龙盛(刘云龙）";

const WALMART_LIST_PATH = "/basicOpen/multiplatform/walmart/list";
const WRITE_RANGE = "A2:V11";
const TIMEOUT_MS = 120000;

function getUsDataDate(): string {
  const now = new Date();
  const usNowText = now.toLocaleString("en-US", { timeZone: "America/New_York" });
  const usNow = new Date(usNowText);
  usNow.setDate(usNow.getDate() - 2);
  return usNow.toISOString().slice(0, 10);
}

function createRunId(): string {
  return `run_${new Date().toISOString().replace(/[-:.TZ]/g, "")}_${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

function toNumber(value: unknown): number {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
}

function buildRows(items: any[], dataDate: string): SheetRow[] {
  const rows: SheetRow[] = items.slice(0, 10).map((item) => {
    const row = new Array(22).fill("");

    row[0] = dataDate; // A 日期
    row[1] = item.store_name || STORE_NAME; // B 店铺
    row[2] = item.item_id || ""; // C 商品ID
    row[3] = item.msku || ""; // D MSKU
    row[4] = item.local_sku || ""; // E SKU
    row[5] = item.local_name || item.local_sku || ""; // F 品名
    row[17] = 6.7; // R 汇率
    row[19] = toNumber(item.wfs_available_quantity); // T WFS可售库存

    return row;
  });

  while (rows.length < 10) {
    rows.push(new Array(22).fill(""));
  }

  return rows;
}

async function main(): Promise<void> {
  const startedAt = Date.now();
  const runId = createRunId();
  const confirmWrite = process.argv.includes("--confirm-write");
  const dryRun = !confirmWrite;

  const writer = new FeishuSheetWriter();
  const logger = new TableOperationLogger(writer, {
    spreadsheetToken: currentReport.spreadsheetToken,
    logSheetId: currentReport.sheets[LOG_SHEET_NAME],
    dryRun,
    confirmWrite,
  });

  let fetchedCount = 0;
  let writtenCount = 0;
  let cleanupSuccess = false;
  let writeSuccess = false;
  let logSuccess = false;
  let failedCount = 0;
  let status = "success";
  let errorMessage = "";
  let remark = "CODEX执行：当日数据测试写入失败，原因：未执行";

  console.log("当日数据测试写入");
  console.log(`运行ID: ${runId}`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log(`目标 Sheet: ${TARGET_SHEET_NAME}`);
  console.log(`目标 Range: ${WRITE_RANGE}`);
  console.log(`测试店铺: ${STORE_NAME}`);
  console.log(`store_id: ${STORE_ID}`);

  try {
    const config = loadConfig();
    config.timeoutMs = TIMEOUT_MS;
    const client = new LingxingClient(config);
    const dataDate = getUsDataDate();

    const response = await client.request<any>({
      method: "POST",
      path: WALMART_LIST_PATH,
      params: {
        offset: 0,
        length: 10,
        store_ids: [STORE_ID],
        status: [0],
      },
      timeoutMs: TIMEOUT_MS,
    });

    const bodyData = response.data;
    const items = Array.isArray(bodyData) ? bodyData : bodyData?.list || [];

    fetchedCount = items.length;
    const rows = buildRows(items, dataDate);

    console.log(`数据日期: ${dataDate}`);
    console.log(`是否抓取成功: 是`);
    console.log(`抓取条数: ${fetchedCount}`);
    console.log("写入预览:");
    console.log(JSON.stringify(rows, null, 2));

    writer.writeCells({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[TARGET_SHEET_NAME],
      sheetName: TARGET_SHEET_NAME,
      range: WRITE_RANGE,
      rows,
      dryRun,
      confirmWrite,
      allowOverwrite: true,
    });

    writeSuccess = true;
    writtenCount = confirmWrite ? rows.length : 0;
    console.log(`是否写入成功: ${writeSuccess ? "是" : "否"}`);

    writer.clearRange({
      spreadsheetToken: currentReport.spreadsheetToken,
      sheetId: currentReport.sheets[TARGET_SHEET_NAME],
      sheetName: TARGET_SHEET_NAME,
      range: WRITE_RANGE,
      dryRun,
      confirmWrite,
    });

    cleanupSuccess = true;
    console.log(`是否清理成功: ${cleanupSuccess ? "是" : "否"}`);
    remark = "CODEX执行：当日数据测试写入，成功后已清理A2:V11";
  } catch (error) {
    failedCount = 1;
    status = "failed";
    errorMessage = error instanceof Error ? error.message : String(error);
    console.log(`是否抓取成功: ${fetchedCount > 0 ? "是" : "否"}`);
    console.log(`抓取条数: ${fetchedCount}`);
    console.log(`是否写入成功: ${writeSuccess ? "是" : "否"}`);
    console.log(`是否清理成功: ${cleanupSuccess ? "是" : "否"}`);
    console.log(`同步失败: ${errorMessage}`);
    if (writeSuccess && !cleanupSuccess) {
      remark = `CODEX执行：写入成功，但清理A2:V11失败，原因：${errorMessage}`;
    } else {
      remark = `CODEX执行：当日数据测试写入失败，原因：${errorMessage}`;
    }
  } finally {
    const durationSeconds = Number(((Date.now() - startedAt) / 1000).toFixed(3));

    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: TASK_NAME,
        targetSheet: TARGET_SHEET_NAME,
        operationType: dryRun ? "dry-run" : "write",
        dataSource: WALMART_LIST_PATH,
        dateRange: "美国时间当天减2天",
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
        remark,
      });
      logSuccess = true;
    } catch (logError) {
      console.log(`记录操作日志失败: ${logError instanceof Error ? logError.message : String(logError)}`);
    }
    console.log(`日志是否写入成功: ${logSuccess ? "是" : "否"}`);
  }
}

main().catch((error) => {
  console.log(`执行失败: ${error instanceof Error ? error.message : String(error)}`);
});

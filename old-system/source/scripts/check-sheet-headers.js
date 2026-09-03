#!/usr/bin/env node
/**
 * 检查飞书两个 Sheet 的当前表头
 * 用法: node scripts/check-sheet-headers.js
 */

const { execFileSync } = require("child_process");
const path = require("path");

const SPREADSHEET_TOKEN = "<REDACTED_FEISHU_SPREADSHEET_TOKEN>";
const LARK_CLI = path.join(__dirname, "lark-cli");

function readHeaders(sheetId, sheetName, endCol = "Z") {
  try {
    const output = execFileSync(LARK_CLI, [
      "sheets", "+cells-get",
      "--spreadsheet-token", SPREADSHEET_TOKEN,
      "--sheet-id", sheetId,
      "--range", `A1:${endCol}1`,
    ], { encoding: "utf8", timeout: 30000 });

    const parsed = JSON.parse(output.trim());
    const rows = parsed?.data?.valueRange?.values || parsed?.values || parsed || [];
    const headers = (Array.isArray(rows) && rows[0]) ? rows[0] : [];

    console.log(`\n=== ${sheetName} (${sheetId}) 表头 ===`);
    headers.forEach((h, i) => {
      const col = i < 26 ? String.fromCharCode(65 + i) : "A" + String.fromCharCode(65 + i - 26);
      if (h) console.log(`  ${col}列: ${h}`);
    });
    if (headers.length === 0) console.log("  （读取为空）");
  } catch (e) {
    console.log(`\n=== ${sheetName} (${sheetId}) 读取失败 ===`);
    console.log("  错误:", e.message);
  }
}

readHeaders("<REDACTED_FEISHU_SHEET_ID>", "悦斯测品汇总/悦斯店铺数据分析", "T");
readHeaders("<REDACTED_FEISHU_SHEET_ID>", "悦斯测品运营日志", "AB");

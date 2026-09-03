import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";
import { execFileSync } from "child_process";

const SPREADSHEET_TOKEN = "<REDACTED_FEISHU_SPREADSHEET_TOKEN>";
const TEST_SHEET_ID = "<REDACTED_FEISHU_SHEET_ID>";
const LARK_CLI = "./scripts/lark-cli";

async function main() {
  const config = loadConfig();
  const client = new LingxingClient(config);

  const result = await client.get<any[]>("/erp/sc/data/seller/allMarketplace");
  const rows = (result.data.data || []).slice(0, 10);

  const cells = [
    [
      { value: "mid" },
      { value: "region" },
      { value: "country" },
      { value: "code" },
    ],
    ...rows.map((item) => [
      { value: String(item.mid ?? "") },
      { value: String(item.region ?? "") },
      { value: String(item.country ?? "") },
      { value: String(item.code ?? "") },
    ]),
  ];

  execFileSync(
    LARK_CLI,
    [
      "sheets",
      "+cells-set",
      "--spreadsheet-token",
      SPREADSHEET_TOKEN,
      "--sheet-id",
      TEST_SHEET_ID,
      "--range",
      `A1:D${cells.length}`,
      "--cells",
      JSON.stringify(cells),
    ],
    { stdio: "inherit" }
  );

  console.log(`已写入飞书测试 Sheet，行数：${cells.length}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

import { loadConfig } from "./config";
import {
  getErrorReason,
  getResponseMessage,
  LingxingApiResponse,
  LingxingClient,
  maskSecret,
} from "./lingxingClient";

const READ_ONLY_TEST_PATH = "/erp/sc/data/seller/allMarketplace";

async function main(): Promise<void> {
  console.log("领星 ERP API 连接测试");

  try {
    const config = loadConfig();
    const client = new LingxingClient(config);

    console.log(`BaseURL: ${config.baseURL}`);
    console.log(`AppID: ${maskSecret(config.appId)}`);
    console.log(`AppSecret: ${maskSecret(config.appSecret)}`);

    const result = await client.get<unknown[]>(READ_ONLY_TEST_PATH);
    const body = result.data;
    const success = result.status >= 200 && result.status < 300 && Number(body?.code) === 0;

    console.log(`API 是否连接成功: ${success ? "是" : "否"}`);
    console.log(`HTTP 状态码: ${result.status}`);
    console.log("接口返回的基础信息:");
    console.log(JSON.stringify(summarizeResponse(body), null, 2));

    if (!success) {
      console.log(`失败原因: ${getResponseMessage(body)}`);
    }
  } catch (error) {
    console.log("API 是否连接成功: 否");
    console.log("HTTP 状态码: N/A");
    console.log(`失败原因: ${getErrorReason(error)}`);
  }
}

function summarizeResponse(body: LingxingApiResponse<unknown[]> | undefined): Record<string, unknown> {
  if (!body) {
    return { message: "No response body" };
  }

  const data = body.data;
  const firstItem = Array.isArray(data) ? data[0] : undefined;

  return {
    code: body.code,
    message: body.message ?? body.msg,
    request_id: body.request_id,
    response_time: body.response_time,
    data_count: Array.isArray(data) ? data.length : undefined,
    first_item: summarizeFirstItem(firstItem),
    error_details: body.error_details,
  };
}

function summarizeFirstItem(firstItem: unknown): unknown {
  if (!firstItem || typeof firstItem !== "object") {
    return undefined;
  }

  const item = firstItem as Record<string, unknown>;

  return {
    mid: item.mid,
    region: item.region,
    country: item.country,
    code: item.code,
  };
}

main();

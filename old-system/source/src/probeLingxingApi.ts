import { loadConfig } from "./config";
import { getErrorReason, LingxingApiResponse, LingxingClient } from "./lingxingClient";

function getArg(name: string, defaultValue = ""): string {
  const prefix = `--${name}=`;
  const arg = process.argv.find((item) => item.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : defaultValue;
}

async function main() {
  const path = getArg("path");
  const methodText = getArg("method", "GET").toUpperCase();
  const paramsText = getArg("params", "{}");
  const timeoutMs = Number(getArg("timeoutMs", "120000"));

  if (!path) {
    console.log("缺少参数：--path=/xxx/xxx");
    return;
  }

  if (methodText !== "GET" && methodText !== "POST") {
    console.log("method 只支持 GET 或 POST");
    return;
  }

  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    console.log("timeoutMs 必须是正数，例如 --timeoutMs=120000");
    return;
  }

  let params: Record<string, unknown> = {};
  try {
    params = JSON.parse(paramsText);
  } catch {
    console.log("params 必须是 JSON 字符串，例如 --params='{\"date\":\"2026-06-02\"}'");
    return;
  }

  const config = {
    ...loadConfig(),
    timeoutMs,
  };
  const client = new LingxingClient(config);

  console.log("领星 API 探测");
  console.log(`method: ${methodText}`);
  console.log(`path: ${path}`);
  console.log(`timeoutMs: ${timeoutMs}`);
  console.log("params:");
  console.log(JSON.stringify(params, null, 2));

  try {
    const body = await client.request<unknown>({
      method: methodText,
      path,
      params,
      timeoutMs,
    });

    printResponseSummary(body);
  } catch (error) {
    console.log("请求失败:");
    console.log(getErrorReason(error));
  }
}

main();

function printResponseSummary(body: LingxingApiResponse<unknown>): void {
  const data = body.data as unknown;

  console.log(`code: ${body.code ?? ""}`);
  console.log(`message/msg: ${body.message ?? body.msg ?? ""}`);
  console.log(`request_id: ${body.request_id ?? ""}`);
  console.log(`response_time: ${body.response_time ?? ""}`);

  if (Array.isArray(data)) {
    printArraySummary("data", data);
    return;
  }

  if (isPlainObject(data)) {
    console.log("data 类型: object");
    console.log("data 字段:");
    console.log(JSON.stringify(Object.keys(data), null, 2));

    const total = data.total;
    const list = data.list;

    if (total !== undefined) {
      console.log(`data.total: ${total}`);
    }

    if (Array.isArray(list)) {
      printArraySummary("data.list", list);
      return;
    }

    console.log("data 预览:");
    console.log(JSON.stringify(data, null, 2).slice(0, 5000));
    return;
  }

  console.log(`data 类型: ${data === null ? "null" : typeof data}`);
  console.log("data:");
  console.log(JSON.stringify(data, null, 2));
}

function printArraySummary(label: string, list: unknown[]): void {
  console.log(`${label} 类型: array`);
  console.log(`${label} 条数: ${list.length}`);
  console.log(`${label} 第一条字段:`);
  console.log(JSON.stringify(isPlainObject(list[0]) ? Object.keys(list[0]) : [], null, 2));
  console.log(`${label} 前3条预览:`);
  console.log(JSON.stringify(list.slice(0, 3), null, 2));
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

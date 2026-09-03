import "dotenv/config";

export interface LingxingConfig {
  baseURL: string;
  appId: string;
  appSecret: string;
  accessToken?: string;
  timeoutMs: number;
}

function readRequiredEnv(name: string): string {
  const value = process.env[name]?.trim();

  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }

  return value;
}

function normalizeBaseURL(value: string): string {
  try {
    const url = new URL(value);
    return url.toString().replace(/\/$/, "");
  } catch {
    throw new Error("LINGXING_BASE_URL must be a valid URL");
  }
}

function readTimeoutMs(): number {
  const raw = process.env.LINGXING_TIMEOUT_MS?.trim();

  if (!raw) {
    return 120000;
  }

  const timeoutMs = Number(raw);

  if (!Number.isInteger(timeoutMs) || timeoutMs <= 0) {
    throw new Error("LINGXING_TIMEOUT_MS must be a positive integer");
  }

  return timeoutMs;
}

export function loadConfig(): LingxingConfig {
  return {
    baseURL: normalizeBaseURL(readRequiredEnv("LINGXING_BASE_URL")),
    appId: readRequiredEnv("LINGXING_APP_ID"),
    appSecret: readRequiredEnv("LINGXING_APP_SECRET"),
    accessToken: process.env.LINGXING_ACCESS_TOKEN?.trim() || undefined,
    timeoutMs: readTimeoutMs(),
  };
}

/**
 * Browser-only design drafts. Never store credentials, access tokens or endpoint URLs here.
 * They are deliberately separate from real Decodo server configuration.
 */
export type DraftCategory = "crawler" | "ai" | "communication" | "bots" | "commerce" | "erp" | "logistics";
export type MeteringMode = "none" | "request" | "tokens" | "traffic" | "image" | "events";
export type DraftState = "draft" | "archived";

export interface ServiceDraft {
  id: string;
  category: DraftCategory;
  provider: string;
  name: string;
  instanceKey: string;
  purpose: string;
  description: string;
  metering: MeteringMode;
  dailyBudget: number;
  status: DraftState;
  updatedAt: string;
}

export interface PolicyDraft {
  id: string;
  name: string;
  scene: string;
  primaryInstance: string;
  fallbackInstance: string;
  dailyLimit: number;
  dailyBudget: number;
  status: DraftState;
}

export interface BrowserDraftStore {
  services: ServiceDraft[];
  policies: PolicyDraft[];
}

export const BUSINESS_PROVIDERS: Record<DraftCategory, string[]> = {
  crawler: ["Decodo", "其他爬虫服务"],
  ai: ["OpenAI", "Gemini", "Claude", "其他 AI 服务"],
  communication: ["飞书", "企业微信", "钉钉", "其他通讯服务"],
  bots: ["飞书群机器人", "企业微信群机器人", "钉钉群机器人", "其他机器人"],
  commerce: ["Walmart", "Amazon", "TEMU", "其他电商平台"],
  erp: ["领星 ERP", "其他 ERP 服务"],
  logistics: ["物流轨迹接口", "海外仓服务", "其他物流服务"],
};

export const METERING_OPTIONS: Array<{ value: MeteringMode; label: string }> = [
  { value: "none", label: "不启用计量" },
  { value: "request", label: "按请求次数" },
  { value: "tokens", label: "按 Token" },
  { value: "traffic", label: "按 GB 流量" },
  { value: "image", label: "按图片任务" },
  { value: "events", label: "按事件数量" },
];

const STORE_KEY = "szzsbj:business-config:v2:design-drafts";

export function readBrowserDrafts(): BrowserDraftStore {
  const fallback: BrowserDraftStore = { services: [], policies: [] };
  try {
    const raw = sessionStorage.getItem(STORE_KEY);
    if (!raw) return fallback;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return fallback;
    const value = parsed as Record<string, unknown>;
    return {
      services: Array.isArray(value.services) ? value.services.filter(isServiceDraft).slice(0, 200) : [],
      policies: Array.isArray(value.policies) ? value.policies.filter(isPolicyDraft).slice(0, 200) : [],
    };
  } catch {
    return fallback;
  }
}

export function writeBrowserDrafts(value: BrowserDraftStore) {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify(value));
  } catch {
    // In private browsing mode, keep the current React state without claiming persistence.
  }
}

export function newDraftId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
}

function isServiceDraft(value: unknown): value is ServiceDraft {
  if (!value || typeof value !== "object") return false;
  const d = value as Record<string, unknown>;
  return typeof d.id === "string"
    && typeof d.category === "string" && d.category in BUSINESS_PROVIDERS
    && typeof d.name === "string" && typeof d.provider === "string"
    && typeof d.instanceKey === "string" && typeof d.purpose === "string"
    && typeof d.description === "string" && typeof d.updatedAt === "string"
    && (d.status === "draft" || d.status === "archived")
    && METERING_OPTIONS.some((option) => option.value === d.metering)
    && typeof d.dailyBudget === "number" && Number.isFinite(d.dailyBudget);
}

function isPolicyDraft(value: unknown): value is PolicyDraft {
  if (!value || typeof value !== "object") return false;
  const d = value as Record<string, unknown>;
  return ["id", "name", "scene", "primaryInstance", "fallbackInstance"].every((key) => typeof d[key] === "string")
    && typeof d.dailyLimit === "number" && Number.isFinite(d.dailyLimit)
    && typeof d.dailyBudget === "number" && Number.isFinite(d.dailyBudget)
    && (d.status === "draft" || d.status === "archived");
}

/** PMC 设置 · WFS API (`/api/pmc/wfs/settings/*`, PRP pmc-wfs-settings §5). Field names follow the contract. */
import { backendRequest, BackendRequestError } from "@/api/backendApi";

export const settingsPrefix = "/api/pmc/wfs/settings";
export const SETTINGS_MANAGE_PERMISSION = "action:pmc:wfs-settings:manage";

export type Region = "美西" | "美中" | "美东" | "待定";
export const REGIONS: Region[] = ["美西", "美中", "美东", "待定"];

export interface RuleRow {
  rule_key: string | null;
  node: string;
  region: string;
  carrier: string;
  channel: string;
  days: number;
  remind_days: number;
  row_effective_date: string;
  notify: string;
  remark: string;
  decided: boolean;
}

export interface RuleVersion {
  version_no: number;
  effective_date: string;
  reason: string;
  created_by: string;
  created_at: string;
}

export interface RuleSet {
  version: RuleVersion;
  rows: RuleRow[];
  sample_rows: number;
}

export interface FcRegion {
  fc: string;
  name: string | null;
  address: string | null;
  zip: string | null;
  city: string | null;
  state: string | null;
  region: Region;
  region_source: "saved" | "state";
  shipments: number;
  updated_by: string | null;
  updated_at: string | null;
}

export interface CreationDefaults {
  transport: "LTL" | "SMALL_PARCEL" | "FTL";
  ship_date_offset: number;
  pallet_boxes: number;
  mixed_boxes: number;
  carrier_opt: "own" | "wm";
}

export interface CreationDefaultsOut extends CreationDefaults {
  source_account_ref: string;
  saved: boolean;
  updated_by: string | null;
  updated_at: string | null;
}

export interface LogisticsChannel {
  provider_id: string | null;
  provider_name: string | null;
  channel_id: string;
  channel_name: string | null;
  method_name: string | null;
  enabled: boolean;
}

export interface SettingsChange {
  entity: string;
  entity_key: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown>;
  reason: string;
  actor: string;
  created_at: string;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const getRules = (signal?: AbortSignal) =>
  backendRequest<RuleSet>(`${settingsPrefix}/rules`, { signal }).then((r) => r.data);

export const listRuleVersions = (signal?: AbortSignal) =>
  backendRequest<{ items: RuleVersion[] }>(`${settingsPrefix}/rules/versions`, { signal }).then((r) => r.data.items);

export const createRuleVersion = (body: { effective_date: string; reason: string; rows: RuleRow[] }) =>
  backendRequest<RuleSet>(`${settingsPrefix}/rules/versions`, json("POST", body)).then((r) => r.data);

/** Server-side page + filters (TABLE_COLUMN_AND_REPORT_RULES: no full-list loading in the browser). */
export interface PageQuery {
  page: number;
  page_size: number;
  keyword?: string;
  search_field?: string;
}
export interface SortQuery<S extends string> { sort_by: S; sort_order: "asc" | "desc" }
export const RULE_SORTS = ["row_no", "node", "days", "row_effective_date"] as const;
export const FC_SORTS = ["fc", "zip", "state", "shipments"] as const;
export const CHANNEL_SORTS = ["provider_name", "channel_id", "channel_name"] as const;
export interface RuleRowQuery extends PageQuery, SortQuery<(typeof RULE_SORTS)[number]> { region?: string; decided?: boolean }
export interface RuleRowPage { version: RuleVersion; items: RuleRow[]; total: number; sample_rows: number; regions: string[] }
export interface FcRegionQuery extends PageQuery, SortQuery<(typeof FC_SORTS)[number]> { region?: Region; state?: string }
export interface FcRegionPage { items: FcRegion[]; total: number; states: string[] }
export interface ChannelQuery extends PageQuery, SortQuery<(typeof CHANNEL_SORTS)[number]> { provider?: string; method?: string; enabled?: boolean }
export interface ChannelPage { items: LogisticsChannel[]; loaded: boolean; total: number; providers: string[]; methods: string[] }

const qs = (query: object) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  return params.toString();
};

export const listRuleRows = (query: RuleRowQuery, signal?: AbortSignal) =>
  backendRequest<RuleRowPage>(`${settingsPrefix}/rules/rows?${qs(query)}`, { signal }).then((r) => r.data);

export const listFcRegions = (query: FcRegionQuery, signal?: AbortSignal) =>
  backendRequest<FcRegionPage>(`${settingsPrefix}/fc-regions?${qs(query)}`, { signal }).then((r) => r.data);

export const updateFcRegion = (fc: string, body: { region: Region; name?: string | null; reason: string }) =>
  backendRequest<FcRegion>(`${settingsPrefix}/fc-regions/${encodeURIComponent(fc)}`, json("PUT", body)).then((r) => r.data);

export const getCreationDefaults = (signal?: AbortSignal) =>
  backendRequest<CreationDefaultsOut>(`${settingsPrefix}/creation-defaults`, { signal }).then((r) => r.data);

export const updateCreationDefaults = (body: CreationDefaults & { reason: string }) =>
  backendRequest<CreationDefaultsOut>(`${settingsPrefix}/creation-defaults`, json("PUT", body)).then((r) => r.data);

export const listLogisticsChannels = (query: ChannelQuery, signal?: AbortSignal) =>
  backendRequest<ChannelPage>(`${settingsPrefix}/logistics-channels?${qs(query)}`, { signal }).then((r) => r.data);

export const listSettingsChanges = (signal?: AbortSignal) =>
  backendRequest<{ items: SettingsChange[]; total: number }>(`${settingsPrefix}/changes?page_size=100`, { signal }).then((r) => r.data);

export function settingsError(error: unknown): string {
  if (error instanceof BackendRequestError) {
    if (error.status === 403) return "没有 WFS 设置的查看 / 维护权限，或没有数据范围";
    if (error.code === "WFS_SETTINGS_EFFECTIVE_DATE_PAST") return "生效日不能早于今天";
    if (error.code === "WFS_SETTINGS_ACCOUNT_REQUIRED") return "当前账号能看到多个来源账号，创建默认值暂不能确定是哪一个";
    if (error.status === 422) return "填写的内容不合法，请检查后重试";
    if (error.status === 503 || error.code === "WFS_SETTINGS_NOT_READY") return "WFS 设置数据库结构尚未更新，请先完成本地迁移";
    if (error.status === 404) return "看板上没有这个仓库";
    return `WFS 设置请求失败：${error.code ?? error.status}`;
  }
  return "WFS 设置请求失败，请稍后重试";
}

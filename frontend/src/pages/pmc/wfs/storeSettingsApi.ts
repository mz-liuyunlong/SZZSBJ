import { backendRequest, BackendRequestError } from "@/api/backendApi";

export const settingsPrefix = "/api/pmc/wfs/settings";

export type MappingState = "unset" | "ok" | "conflict" | "unreviewed";

export interface StoreSetting {
  source_account_ref: string;
  store_id: string;
  store_name: string | null;
  suggested_code: string | null;
  walmart_store_code: string | null;
  reviewed_code: string | null;
  mapping_state: MappingState;
  its_enabled: boolean;
  creation_enabled: boolean;
  note: string | null;
  actor_uid: string | null;
  updated_at: string | null;
}

export interface StoreSettingCommand {
  source_account_ref: string;
  walmart_store_code: string;
  its_enabled: boolean;
  creation_enabled: boolean;
  note?: string | null;
}

export const listStoreSettings = (signal?: AbortSignal) =>
  backendRequest<{ items: StoreSetting[]; total: number }>(`${settingsPrefix}/stores`, { signal });

export const saveStoreSetting = (storeId: string, body: StoreSettingCommand) =>
  backendRequest<StoreSetting>(`${settingsPrefix}/stores/${encodeURIComponent(storeId)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });

export function settingsError(error: unknown): string {
  if (error instanceof BackendRequestError) {
    if (error.code === "WFS_STORE_CODE_TAKEN") return "该 Walmart 店铺代码已被另一个店铺使用";
    if (error.status === 401) return "登录已失效，请重新登录";
    if (error.status === 403) return "没有 WFS 设置的修改权限或店铺数据范围";
    if (error.status === 404) return "店铺不在当前账号范围内";
    if (error.status === 422) return "店铺代码格式应为 HK 或 CN 加 4 位数字";
  }
  return "WFS 设置请求失败，请重试";
}

import { backendRequest } from "@/api/backendApi";
import {
  actionPermissionGroups,
  createDefaultRolePermissions,
  pagePermissionGroups,
} from "@/pages/settings/roleManagementMockData";
import type {
  RoleFormValues,
  RoleManagementRow,
  RolePermissionState,
} from "@/pages/settings/roleManagementTypes";

interface BackendRole {
  id: string;
  role_key: string;
  name: string;
  description: string | null;
  is_system: boolean;
  user_count: number;
  permission_keys: string[];
}

const uiPermissionMap: Record<string, string[]> = {
  今日销售: ["sales:daily-sales:read"],
  今日利润: ["sales:daily-sales:read"],
  产品管理: ["products:read"],
  Listing管理: ["products:read"],
  每日销售: ["sales:daily-sales:read"],
  订单利润: ["sales:daily-sales:read"],
  退款管理: ["aftersales:refund-management:read"],
  库存明细: ["warehouse:wfs-fee-alert:read"],
  库存预警: ["warehouse:wfs-fee-alert:read"],
  采购计划: ["pmc:purchase:read"],
  采购单: ["pmc:purchase:read"],
  用户管理: ["settings:users:read"],
  角色管理: ["settings:roles:read"],
  费用规则: ["business-rules:read"],
  查看: [
    "products:read",
    "sales:daily-sales:read",
    "aftersales:refund-management:read",
    "warehouse:wfs-fee-alert:read",
    "pmc:purchase:read",
  ],
  新增: ["settings:users:write", "settings:roles:write"],
  编辑: ["settings:users:write", "settings:roles:write", "business-rules:write"],
  删除: ["settings:users:write", "settings:roles:write"],
  导出: ["products:read", "sales:daily-sales:read"],
  下载: ["products:read", "sales:daily-sales:read"],
  设置角色: ["settings:roles:write"],
  重置密码: ["settings:users:write"],
  停用用户: ["settings:users:write"],
  删除用户: ["settings:users:write"],
  同步产品资料: ["integrations:execute"],
  同步Listing: ["integrations:execute"],
};

function makeRoleKey(name: string): string {
  const ascii = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");

  return ascii || `custom_${Date.now()}`;
}

function toRow(role: BackendRole): RoleManagementRow {
  return {
    id: role.role_key,
    roleKey: role.role_key,
    name: role.name,
    description: role.description || "自定义角色",
    preset: role.is_system,
    userCount: role.user_count,
    permissionKeys: role.permission_keys,
  };
}

function allBooleanItems() {
  return [
    ...pagePermissionGroups.flatMap((group) => group.items),
    ...actionPermissionGroups.flatMap((group) => group.items),
  ];
}

export function permissionKeysToState(permissionKeys: string[]): RolePermissionState {
  const state = createDefaultRolePermissions();
  const keySet = new Set(permissionKeys);

  allBooleanItems().forEach((item) => {
    const mappedKeys = uiPermissionMap[item] ?? [];
    const checked = mappedKeys.length === 0
      ? true
      : mappedKeys.some((permissionKey) => keySet.has(permissionKey));

    if (item in state.pagePermissions) state.pagePermissions[item] = checked;
    if (item in state.actionPermissions) state.actionPermissions[item] = checked;
  });

  return state;
}

export function stateToPermissionKeys(
  state: RolePermissionState,
  existingPermissionKeys: string[],
): string[] {
  const next = new Set(existingPermissionKeys);

  for (const [item, mappedKeys] of Object.entries(uiPermissionMap)) {
    const checked = state.pagePermissions[item] ?? state.actionPermissions[item];
    if (checked === undefined) continue;

    mappedKeys.forEach((permissionKey) => {
      if (checked) next.add(permissionKey);
      else next.delete(permissionKey);
    });
  }

  return Array.from(next).sort();
}

export async function listRoles(): Promise<RoleManagementRow[]> {
  const response = await backendRequest<BackendRole[]>("/api/settings/roles");
  return response.data.map(toRow);
}

export async function createRole(values: RoleFormValues): Promise<RoleManagementRow> {
  const response = await backendRequest<BackendRole>("/api/settings/roles", {
    method: "POST",
    body: JSON.stringify({
      role_key: makeRoleKey(values.name),
      name: values.name.trim(),
      description: values.description?.trim() || "自定义角色",
      permission_keys: [],
    }),
  });

  return toRow(response.data);
}

export async function saveRolePermissions(
  role: RoleManagementRow,
  permissions: RolePermissionState,
): Promise<RoleManagementRow> {
  const response = await backendRequest<BackendRole>(`/api/settings/roles/${role.roleKey}`, {
    method: "PATCH",
    body: JSON.stringify({
      permission_keys: stateToPermissionKeys(permissions, role.permissionKeys),
    }),
  });

  return toRow(response.data);
}

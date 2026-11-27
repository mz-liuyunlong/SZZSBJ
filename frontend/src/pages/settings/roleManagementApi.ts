import { backendRequest } from "@/api/backendApi";
import { navigation } from "@/config/navigation";
import { getPagePermissionKey } from "@/shared/permissions/mockAccess";
import type {
  PermissionGroup,
  RoleAuditEvent,
  RoleDataScopeEntry,
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
  version: number;
}

interface BackendPermissionItem {
  permission_key: string;
  name: string;
  description: string | null;
  permission_type: "page" | "action" | "field";
  module_key: string;
  page_key: string;
  action_key: string | null;
  field_key: string | null;
  risk_level: "normal" | "high";
  sort_order: number;
}

interface BackendPermissionPage {
  page_key: string;
  name: string;
  permission_key: string;
  sort_order: number;
  actions: BackendPermissionItem[];
  fields: BackendPermissionItem[];
}

interface BackendPermissionModule {
  module_key: string;
  name: string;
  sort_order: number;
  pages: BackendPermissionPage[];
}

interface BackendPermissionCatalog {
  version: string;
  modules: BackendPermissionModule[];
}

interface BackendDataScopeEntry {
  scope_type: RoleDataScopeEntry["scopeType"];
  scope_value: string;
}

interface BackendRoleDataScope {
  role_key: string;
  items: BackendDataScopeEntry[];
}

interface BackendAuditEvent {
  id: string;
  actor_user_id: number | null;
  event_type: string;
  target_type: string;
  target_key: string;
  request_id: string | null;
  request_ip: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface RolePermissionCatalog {
  pagePermissionGroups: PermissionGroup[];
  actionPermissionGroups: PermissionGroup[];
  fieldPermissionGroups: PermissionGroup[];
  permissionLabels: Record<string, string>;
  permissionDescriptions: Record<string, string>;
  highRiskPermissions: ReadonlySet<string>;
  activeBackendPermissionKeys: ReadonlySet<string>;
}

export const emptyRolePermissionCatalog: RolePermissionCatalog = {
  pagePermissionGroups: [],
  actionPermissionGroups: [],
  fieldPermissionGroups: [],
  permissionLabels: {},
  permissionDescriptions: {},
  highRiskPermissions: new Set<string>(),
  activeBackendPermissionKeys: new Set<string>(),
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
    version: role.version,
  };
}

function createBooleanState(groups: PermissionGroup[]) {
  return Object.fromEntries(
    groups.flatMap((group) => group.items.map((item) => [item, false])),
  ) as Record<string, boolean>;
}

function catalogPermissionKeys(catalog: RolePermissionCatalog) {
  return new Set([
    ...catalog.pagePermissionGroups.flatMap((group) => group.items),
    ...catalog.actionPermissionGroups.flatMap((group) => group.items),
    ...catalog.fieldPermissionGroups.flatMap((group) => group.items),
  ]);
}

export function buildRolePermissionCatalog(
  backendCatalog: BackendPermissionCatalog,
): RolePermissionCatalog {
  // Navigation is the sole current route registry. One existing grant can cover
  // several routes (e.g. new-product/launch-tracking and product/clearance).
  const liveRoutes = new Map<string, string[]>();
  // The current Dashboard and Products modules have only these real pages.
  // Do not expose retired placeholders as page permissions.
  const currentPageKeys: Readonly<Record<string, readonly string[]>> = {
    dashboard: ["dashboard_today_sales"],
    products: [
      "products_product_management", "products_clearance_center",
      "products_listing_management", "products_new_product_analysis",
      "products_launch_tracking",
    ],
  };
  navigation.forEach((group) => group.children.forEach((page) => {
    const allowed = currentPageKeys[group.key];
    if (allowed && !allowed.includes(page.key)) return;
    if (page.status === "hidden" || page.status === "disabled") return;
    const key = getPagePermissionKey(page);
    // The exchange-rate route is intentionally super-admin-only.
    if (key === "page:finance:fx-rates:view") return;
    const titles = liveRoutes.get(key) ?? [];
    if (!titles.includes(page.title)) titles.push(page.title);
    liveRoutes.set(key, titles);
  }));

  const permissionLabels: Record<string, string> = {};
  const permissionDescriptions: Record<string, string> = {};
  const highRiskPermissions = new Set<string>();
  const activeBackendPermissionKeys = new Set<string>();
  const pagePermissionGroups: PermissionGroup[] = [];
  const actionPermissionGroups: PermissionGroup[] = [];
  const fieldPermissionGroups: PermissionGroup[] = [];

  backendCatalog.modules.forEach((module) => {
    const pageItems: string[] = [];
    module.pages.forEach((page) => {
      activeBackendPermissionKeys.add(page.permission_key);
      page.actions.forEach((item) => activeBackendPermissionKeys.add(item.permission_key));
      page.fields.forEach((item) => activeBackendPermissionKeys.add(item.permission_key));
      const titles = liveRoutes.get(page.permission_key);
      if (!titles) return; // Retired page: hide it, do not revoke historic grants.
      const displayName = titles.join(" / ");
      pageItems.push(page.permission_key);
      permissionLabels[page.permission_key] = displayName;
      permissionDescriptions[page.permission_key] = `允许进入并查看「${titles.join("、")}」页面`;

      if (page.actions.length > 0) {
        const items = page.actions.map((action) => {
          permissionLabels[action.permission_key] = action.name;
          permissionDescriptions[action.permission_key] =
            action.description || `${displayName}：${action.name}`;
          if (action.risk_level === "high") highRiskPermissions.add(action.permission_key);
          return action.permission_key;
        });
        actionPermissionGroups.push({title: `${module.name} / ${displayName}`, items});
      }
      if (page.fields.length > 0) {
        const items = page.fields.map((field) => {
          permissionLabels[field.permission_key] = field.name;
          permissionDescriptions[field.permission_key] =
            field.description || `${displayName}字段：${field.name}`;
          if (field.risk_level === "high") highRiskPermissions.add(field.permission_key);
          return field.permission_key;
        });
        fieldPermissionGroups.push({title: `${module.name} / ${displayName}`, items});
      }
    });
    if (pageItems.length > 0) pagePermissionGroups.push({title: module.name, items: pageItems});
  });
  return {
    pagePermissionGroups, actionPermissionGroups, fieldPermissionGroups,
    permissionLabels, permissionDescriptions, highRiskPermissions,
    activeBackendPermissionKeys,
  };
}

export function createDefaultRolePermissions(
  catalog: RolePermissionCatalog = emptyRolePermissionCatalog,
): RolePermissionState {
  return {
    pagePermissions: createBooleanState(catalog.pagePermissionGroups),
    actionPermissions: createBooleanState(catalog.actionPermissionGroups),
    fieldPermissions: createBooleanState(catalog.fieldPermissionGroups),
  };
}

export function permissionKeysToState(
  permissionKeys: string[],
  catalog: RolePermissionCatalog = emptyRolePermissionCatalog,
): RolePermissionState {
  const state = createDefaultRolePermissions(catalog);
  const keySet = new Set(permissionKeys);

  Object.keys(state.pagePermissions).forEach((permissionKey) => {
    state.pagePermissions[permissionKey] = keySet.has(permissionKey);
  });
  Object.keys(state.actionPermissions).forEach((permissionKey) => {
    state.actionPermissions[permissionKey] = keySet.has(permissionKey);
  });
  Object.keys(state.fieldPermissions).forEach((permissionKey) => {
    state.fieldPermissions[permissionKey] = keySet.has(permissionKey);
  });

  return state;
}

export function stateToPermissionKeys(
  state: RolePermissionState,
  catalog: RolePermissionCatalog,
): string[] {
  const catalogKeys = catalogPermissionKeys(catalog);
  return [
    ...Object.entries(state.pagePermissions),
    ...Object.entries(state.actionPermissions),
    ...Object.entries(state.fieldPermissions),
  ]
    .filter(([permissionKey, enabled]) => enabled && catalogKeys.has(permissionKey))
    .map(([permissionKey]) => permissionKey)
    .sort();
}

export function normalizeRoleDataScopes(items: RoleDataScopeEntry[]): RoleDataScopeEntry[] {
  const seen = new Set<string>();
  return items.flatMap((item) => {
    const scopeValue = item.scopeValue.trim();
    const identity = `${item.scopeType}:${scopeValue}`;
    if (!scopeValue || seen.has(identity)) return [];
    seen.add(identity);
    return [{ scopeType: item.scopeType, scopeValue }];
  });
}

export async function loadRoleManagementData(): Promise<{
  roles: RoleManagementRow[];
  permissionCatalog: RolePermissionCatalog;
}> {
  const [rolesResponse, catalogResponse] = await Promise.all([
    backendRequest<BackendRole[]>("/api/settings/rbac/roles"),
    backendRequest<BackendPermissionCatalog>("/api/settings/rbac/catalog"),
  ]);

  return {
    roles: rolesResponse.data.map(toRow),
    permissionCatalog: buildRolePermissionCatalog(catalogResponse.data),
  };
}

export async function createRole(values: RoleFormValues): Promise<RoleManagementRow> {
  const response = await backendRequest<BackendRole>("/api/settings/rbac/roles", {
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
  catalog: RolePermissionCatalog,
): Promise<RoleManagementRow> {
  const visibleKeys = catalogPermissionKeys(catalog);
  const retainedKeys = role.permissionKeys.filter((key) =>
    catalog.activeBackendPermissionKeys.has(key) && !visibleKeys.has(key),
  );
  const permissionKeys = [...new Set([
    ...retainedKeys,
    ...stateToPermissionKeys(permissions, catalog),
  ])].sort();
  const response = await backendRequest<BackendRole>(
    `/api/settings/rbac/roles/${role.roleKey}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        permission_keys: permissionKeys,
        expected_version: role.version,
      }),
    },
  );

  return toRow(response.data);
}

export async function loadRoleDataScopes(roleKey: string): Promise<RoleDataScopeEntry[]> {
  const response = await backendRequest<BackendRoleDataScope>(
    `/api/settings/rbac/roles/${roleKey}/data-scopes`,
  );
  return response.data.items.map((item) => ({
    scopeType: item.scope_type,
    scopeValue: item.scope_value,
  }));
}

export async function saveRoleDataScopes(
  roleKey: string,
  items: RoleDataScopeEntry[],
): Promise<RoleDataScopeEntry[]> {
  const normalizedItems = normalizeRoleDataScopes(items);
  const response = await backendRequest<BackendRoleDataScope>(
    `/api/settings/rbac/roles/${roleKey}/data-scopes`,
    {
      method: "PUT",
      body: JSON.stringify({
        items: normalizedItems.map((item) => ({
          scope_type: item.scopeType,
          scope_value: item.scopeValue,
        })),
      }),
    },
  );
  return response.data.items.map((item) => ({
    scopeType: item.scope_type,
    scopeValue: item.scope_value,
  }));
}

export async function loadRoleAuditEvents(limit = 100): Promise<RoleAuditEvent[]> {
  const response = await backendRequest<BackendAuditEvent[]>(
    `/api/settings/rbac/audit-events?limit=${limit}`,
  );
  return response.data.map((item) => ({
    id: item.id,
    actorUserId: item.actor_user_id ?? undefined,
    eventType: item.event_type,
    targetType: item.target_type,
    targetKey: item.target_key,
    requestId: item.request_id ?? undefined,
    requestIp: item.request_ip ?? undefined,
    userAgent: item.user_agent ?? undefined,
    createdAt: item.created_at,
  }));
}

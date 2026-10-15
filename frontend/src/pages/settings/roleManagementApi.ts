import { backendRequest } from "@/api/backendApi";
import type {
  PermissionGroup,
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

export interface RolePermissionCatalog {
  pagePermissionGroups: PermissionGroup[];
  actionPermissionGroups: PermissionGroup[];
  fieldPermissionGroups: PermissionGroup[];
  permissionLabels: Record<string, string>;
  permissionDescriptions: Record<string, string>;
  highRiskPermissions: ReadonlySet<string>;
}

export const emptyRolePermissionCatalog: RolePermissionCatalog = {
  pagePermissionGroups: [],
  actionPermissionGroups: [],
  fieldPermissionGroups: [],
  permissionLabels: {},
  permissionDescriptions: {},
  highRiskPermissions: new Set<string>(),
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
  const permissionLabels: Record<string, string> = {};
  const permissionDescriptions: Record<string, string> = {};
  const highRiskPermissions = new Set<string>();
  const pagePermissionGroups: PermissionGroup[] = [];
  const actionPermissionGroups: PermissionGroup[] = [];
  const fieldPermissionGroups: PermissionGroup[] = [];

  backendCatalog.modules.forEach((module) => {
    const pageItems: string[] = [];

    module.pages.forEach((page) => {
      pageItems.push(page.permission_key);
      permissionLabels[page.permission_key] = page.name;
      permissionDescriptions[page.permission_key] = `允许进入并查看「${page.name}」页面`;

      if (page.actions.length > 0) {
        const items = page.actions.map((action) => {
          permissionLabels[action.permission_key] = action.name;
          permissionDescriptions[action.permission_key] =
            action.description || `${page.name}：${action.name}`;
          if (action.risk_level === "high") {
            highRiskPermissions.add(action.permission_key);
          }
          return action.permission_key;
        });
        actionPermissionGroups.push({
          title: `${module.name} / ${page.name}`,
          items,
        });
      }

      if (page.fields.length > 0) {
        const items = page.fields.map((field) => {
          permissionLabels[field.permission_key] = field.name;
          permissionDescriptions[field.permission_key] =
            field.description || `${page.name}字段：${field.name}`;
          if (field.risk_level === "high") {
            highRiskPermissions.add(field.permission_key);
          }
          return field.permission_key;
        });
        fieldPermissionGroups.push({
          title: `${module.name} / ${page.name}`,
          items,
        });
      }
    });

    if (pageItems.length > 0) {
      pagePermissionGroups.push({ title: module.name, items: pageItems });
    }
  });

  return {
    pagePermissionGroups,
    actionPermissionGroups,
    fieldPermissionGroups,
    permissionLabels,
    permissionDescriptions,
    highRiskPermissions,
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
  const response = await backendRequest<BackendRole>(
    `/api/settings/rbac/roles/${role.roleKey}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        permission_keys: stateToPermissionKeys(permissions, catalog),
        expected_version: role.version,
      }),
    },
  );

  return toRow(response.data);
}

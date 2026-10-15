import { backendRequest } from "@/api/backendApi";
import { navigation } from "@/config/navigation";
import { getPagePermissionKey } from "@/shared/permissions/mockAccess";
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
}

interface BackendPermission {
  permission_key: string;
  name: string;
  group_key: string;
  description: string | null;
}

export interface RolePermissionCatalog {
  pagePermissionGroups: PermissionGroup[];
  actionPermissionGroups: PermissionGroup[];
  permissionLabels: Record<string, string>;
  permissionDescriptions: Record<string, string>;
}

export const emptyRolePermissionCatalog: RolePermissionCatalog = {
  pagePermissionGroups: [],
  actionPermissionGroups: [],
  permissionLabels: {},
  permissionDescriptions: {},
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

function createBooleanState(groups: PermissionGroup[]) {
  return Object.fromEntries(
    groups.flatMap((group) => group.items.map((item) => [item, false])),
  ) as Record<string, boolean>;
}

function catalogPermissionKeys(catalog: RolePermissionCatalog) {
  return new Set([
    ...catalog.pagePermissionGroups.flatMap((group) => group.items),
    ...catalog.actionPermissionGroups.flatMap((group) => group.items),
  ]);
}

function buildRolePermissionCatalog(
  backendPermissions: BackendPermission[],
): RolePermissionCatalog {
  const backendPermissionKeys = new Set(
    backendPermissions.map((permission) => permission.permission_key),
  );
  const permissionLabels: Record<string, string> = {};
  const permissionDescriptions: Record<string, string> = {};

  backendPermissions.forEach((permission) => {
    permissionLabels[permission.permission_key] = permission.name;
    if (permission.description) {
      permissionDescriptions[permission.permission_key] = permission.description;
    }
  });

  const navigationPermissionKeys = new Set<string>();
  const pageLabelsByPermissionKey = new Map<string, string[]>();

  const pagePermissionGroups = navigation
    .map((group) => {
      const items: string[] = [];
      const groupPermissionKeys = new Set<string>();

      group.children.forEach((page) => {
        if (page.status === "hidden" || page.status === "disabled") return;

        const permissionKey = getPagePermissionKey(page);
        if (!backendPermissionKeys.has(permissionKey)) return;

        navigationPermissionKeys.add(permissionKey);

        if (!groupPermissionKeys.has(permissionKey)) {
          groupPermissionKeys.add(permissionKey);
          items.push(permissionKey);
        }

        const labels = pageLabelsByPermissionKey.get(permissionKey) ?? [];
        if (!labels.includes(page.title)) labels.push(page.title);
        pageLabelsByPermissionKey.set(permissionKey, labels);
      });

      return { title: group.title, items };
    })
    .filter((group) => group.items.length > 0);

  pageLabelsByPermissionKey.forEach((labels, permissionKey) => {
    permissionLabels[permissionKey] = labels.join(" / ");
  });

  const actionGroupsByTitle = new Map<string, string[]>();

  backendPermissions.forEach((permission) => {
    const permissionKey = permission.permission_key;
    if (navigationPermissionKeys.has(permissionKey)) return;

    const title = permission.group_key || "功能权限";
    const items = actionGroupsByTitle.get(title) ?? [];
    if (!items.includes(permissionKey)) items.push(permissionKey);
    actionGroupsByTitle.set(title, items);
  });

  const actionPermissionGroups = Array.from(actionGroupsByTitle.entries()).map(
    ([title, items]) => ({ title, items }),
  );

  return {
    pagePermissionGroups,
    actionPermissionGroups,
    permissionLabels,
    permissionDescriptions,
  };
}

export function createDefaultRolePermissions(
  catalog: RolePermissionCatalog = emptyRolePermissionCatalog,
): RolePermissionState {
  return {
    pagePermissions: createBooleanState(catalog.pagePermissionGroups),
    actionPermissions: createBooleanState(catalog.actionPermissionGroups),
    fieldPermissions: {},
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

  return state;
}

export function stateToPermissionKeys(
  state: RolePermissionState,
  existingPermissionKeys: string[],
  catalog: RolePermissionCatalog,
): string[] {
  const catalogKeys = catalogPermissionKeys(catalog);
  const next = new Set(
    existingPermissionKeys.filter((permissionKey) => !catalogKeys.has(permissionKey)),
  );

  catalog.pagePermissionGroups.forEach((group) => {
    group.items.forEach((permissionKey) => {
      if (state.pagePermissions[permissionKey] === true) {
        next.add(permissionKey);
      }
    });
  });

  catalog.actionPermissionGroups.forEach((group) => {
    group.items.forEach((permissionKey) => {
      if (state.actionPermissions[permissionKey] === true) {
        next.add(permissionKey);
      }
    });
  });

  return Array.from(next).sort();
}

export async function loadRoleManagementData(): Promise<{
  roles: RoleManagementRow[];
  permissionCatalog: RolePermissionCatalog;
}> {
  const [rolesResponse, permissionsResponse] = await Promise.all([
    backendRequest<BackendRole[]>("/api/settings/roles"),
    backendRequest<BackendPermission[]>("/api/settings/permissions"),
  ]);

  return {
    roles: rolesResponse.data.map(toRow),
    permissionCatalog: buildRolePermissionCatalog(permissionsResponse.data),
  };
}

export async function listRoles(): Promise<RoleManagementRow[]> {
  const data = await loadRoleManagementData();
  return data.roles;
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
  catalog: RolePermissionCatalog,
): Promise<RoleManagementRow> {
  const response = await backendRequest<BackendRole>(`/api/settings/roles/${role.roleKey}`, {
    method: "PATCH",
    body: JSON.stringify({
      permission_keys: stateToPermissionKeys(permissions, role.permissionKeys, catalog),
    }),
  });

  return toRow(response.data);
}

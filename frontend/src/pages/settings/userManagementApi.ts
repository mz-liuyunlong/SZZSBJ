import { backendRequest } from "@/api/backendApi";
import {
  type FeishuDirectorySearchResult,
  type FeishuDirectoryUser,
  type UserFormValues,
  type UserManagementRow,
  type UserRoleName,
  type UserRoleOption,
} from "@/pages/settings/userManagementTypes";
import type { RoleDataScopeEntry } from "@/pages/settings/roleManagementTypes";
import type { EffectiveUserDataScopeEntry } from "@/pages/settings/components/UserDataScopeModal";

interface BackendUser {
  id: number;
  username: string;
  display_name: string | null;
  phone: string | null;
  email: string | null;
  is_active: boolean;
  is_super_admin: boolean;
  role_keys: string[];
  role_names: string[];
  feishu_name: string | null;
  feishu_open_id: string | null;
  feishu_user_id: string | null;
  feishu_union_id: string | null;
  feishu_employee_id: string | null;
  feishu_department_ids: string[];
  feishu_last_synced_at: string | null;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

interface BackendFeishuDirectoryUser {
  name: string;
  open_id: string;
  user_id: string | null;
  union_id: string | null;
  employee_id: string | null;
  department_ids: string[];
}

interface BackendFeishuDirectorySearchResult {
  query_name: string;
  matched_count: number;
  is_unique: boolean;
  users: BackendFeishuDirectoryUser[];
}

interface BackendRoleOption {
  role_key: string;
  name: string;
  description: string | null;
  is_system: boolean;
  assignable: boolean;
}

interface BackendDataScopeEntry {
  scope_type: RoleDataScopeEntry["scopeType"];
  scope_value: string;
}

interface BackendEffectiveDataScopeEntry extends BackendDataScopeEntry {
  source: "user" | "role";
}

interface BackendUserDataScope {
  user_id: number;
  items: BackendDataScopeEntry[];
  role_items: BackendDataScopeEntry[];
  effective_items: BackendEffectiveDataScopeEntry[];
}

export interface UserDataScopeState {
  items: RoleDataScopeEntry[];
  roleItems: RoleDataScopeEntry[];
  effectiveItems: EffectiveUserDataScopeEntry[];
}

function toScopeEntry(item: BackendDataScopeEntry): RoleDataScopeEntry {
  return { scopeType: item.scope_type, scopeValue: item.scope_value };
}

function toUserDataScopeState(data: BackendUserDataScope): UserDataScopeState {
  return {
    items: data.items.map(toScopeEntry),
    roleItems: data.role_items.map(toScopeEntry),
    effectiveItems: data.effective_items.map((item) => ({
      ...toScopeEntry(item),
      source: item.source,
    })),
  };
}

function optionalString(value: string | undefined): string | undefined {
  const normalized = value?.trim();
  return normalized || undefined;
}

function toFeishuDirectoryUser(user: BackendFeishuDirectoryUser): FeishuDirectoryUser {
  return {
    name: user.name,
    openId: user.open_id,
    userId: user.user_id ?? undefined,
    unionId: user.union_id ?? undefined,
    employeeId: user.employee_id ?? undefined,
    departmentIds: user.department_ids,
  };
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16).replace("T", " ");
  return date.toLocaleString("zh-CN", {
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function toRoleOptions(roles: BackendRoleOption[]): UserRoleOption[] {
  return roles.map((role) => ({
    key: role.role_key,
    name: role.name,
    description: role.description ?? undefined,
    isSystem: role.is_system,
    assignable: role.assignable,
  }));
}

function roleNameFromKey(roleKey: string, roleOptions: UserRoleOption[]): UserRoleName {
  return roleOptions.find((role) => role.key === roleKey)?.name ?? roleKey;
}

function roleKeysFromNames(names: UserRoleName[], roleOptions: UserRoleOption[]): string[] {
  return names.flatMap((name) => {
    const role = roleOptions.find((item) => item.name === name && item.assignable);
    return role ? [role.key] : [];
  });
}

function toUserRow(user: BackendUser, roleOptions: UserRoleOption[]): UserManagementRow {
  const roleNames = user.role_keys.length > 0
    ? user.role_keys.map((roleKey) => roleNameFromKey(roleKey, roleOptions))
    : user.role_names;

  return {
    id: String(user.id),
    username: user.username,
    realName: user.display_name || user.username,
    phone: user.phone || "-",
    email: user.email || "-",
    status: user.is_active ? "启用" : "停用",
    roles: user.is_super_admin
      ? ["超级管理员", ...roleNames.filter((name) => name !== "管理员")]
      : roleNames,
    isSuperAdmin: user.is_super_admin,
    feishuName: user.feishu_name ?? undefined,
    feishuOpenId: user.feishu_open_id ?? undefined,
    feishuUserId: user.feishu_user_id ?? undefined,
    feishuUnionId: user.feishu_union_id ?? undefined,
    feishuEmployeeId: user.feishu_employee_id ?? undefined,
    feishuDepartmentIds: user.feishu_department_ids ?? [],
    createdAt: formatDate(user.created_at),
    lastLoginAt: formatDate(user.last_login_at),
  };
}

export async function loadUserManagementData(): Promise<{
  users: UserManagementRow[];
  roleOptions: UserRoleOption[];
}> {
  const [usersResponse, roleOptionsResponse] = await Promise.all([
    backendRequest<BackendUser[]>("/api/settings/users"),
    backendRequest<BackendRoleOption[]>("/api/settings/user-role-options"),
  ]);

  const roleOptions = toRoleOptions(roleOptionsResponse.data);
  return {
    roleOptions,
    users: usersResponse.data.map((user) => toUserRow(user, roleOptions)),
  };
}

export async function searchFeishuUsers(name: string): Promise<FeishuDirectorySearchResult> {
  const response = await backendRequest<BackendFeishuDirectorySearchResult>(
    `/api/settings/users/feishu/search?name=${encodeURIComponent(name.trim())}`,
  );

  return {
    queryName: response.data.query_name,
    matchedCount: response.data.matched_count,
    isUnique: response.data.is_unique,
    users: response.data.users.map(toFeishuDirectoryUser),
  };
}

export async function createUser(
  values: UserFormValues,
  roleOptions: UserRoleOption[],
): Promise<string> {
  const created = await backendRequest<BackendUser>("/api/settings/users", {
    method: "POST",
    body: JSON.stringify({
      username: values.username.trim(),
      password: optionalString(values.password),
      display_name: values.realName.trim(),
      phone: values.phone?.trim() || undefined,
      email: values.email?.trim() || undefined,
      feishu_name: optionalString(values.feishuName),
      feishu_open_id: optionalString(values.feishuOpenId),
      feishu_user_id: optionalString(values.feishuUserId),
      feishu_union_id: optionalString(values.feishuUnionId),
      feishu_employee_id: optionalString(values.feishuEmployeeId),
      feishu_department_ids: values.feishuDepartmentIds?.length
        ? values.feishuDepartmentIds
        : undefined,
      role_keys: roleKeysFromNames(values.roles, roleOptions),
    }),
  });
  return String(created.data.id);
}

export async function updateUser(
  userId: string,
  values: UserFormValues,
): Promise<void> {
  await backendRequest<BackendUser>(`/api/settings/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({
      display_name: values.realName.trim(),
      phone: values.phone?.trim() || undefined,
      email: values.email?.trim() || undefined,
      feishu_name: optionalString(values.feishuName),
      feishu_open_id: optionalString(values.feishuOpenId),
      feishu_user_id: optionalString(values.feishuUserId),
      feishu_union_id: optionalString(values.feishuUnionId),
      feishu_employee_id: optionalString(values.feishuEmployeeId),
      feishu_department_ids: values.feishuDepartmentIds?.length
        ? values.feishuDepartmentIds
        : undefined,
    }),
  });
}

export async function updateUserRoles(
  userId: string,
  roles: UserRoleName[],
  roleOptions: UserRoleOption[],
): Promise<void> {
  await backendRequest<BackendUser>(`/api/settings/users/${userId}/roles`, {
    method: "PUT",
    body: JSON.stringify({
      role_keys: roleKeysFromNames(roles, roleOptions),
    }),
  });
}

export async function updateUserStatus(userId: string, enabled: boolean): Promise<void> {
  await backendRequest<BackendUser>(`/api/settings/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: enabled }),
  });
}

export async function resetUserPassword(userId: string, newPassword: string): Promise<void> {
  await backendRequest<BackendUser>(`/api/settings/users/${userId}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ new_password: newPassword }),
  });
}

export async function deleteUserPermanently(userId: string): Promise<void> {
  await backendRequest<BackendUser>(`/api/settings/users/${userId}`, {
    method: "DELETE",
  });
}

export async function loadUserDataScopes(userId: string): Promise<UserDataScopeState> {
  const response = await backendRequest<BackendUserDataScope>(
    `/api/settings/rbac/users/${userId}/data-scopes`,
  );
  return toUserDataScopeState(response.data);
}

export async function saveUserDataScopes(
  userId: string,
  items: RoleDataScopeEntry[],
): Promise<UserDataScopeState> {
  const normalized = items.flatMap((item) => {
    const scopeValue = item.scopeValue.trim();
    return scopeValue ? [{ scope_type: item.scopeType, scope_value: scopeValue }] : [];
  });
  const response = await backendRequest<BackendUserDataScope>(
    `/api/settings/rbac/users/${userId}/data-scopes`,
    { method: "PUT", body: JSON.stringify({ items: normalized }) },
  );
  return toUserDataScopeState(response.data);
}


export interface OwnerBindingCandidate {
  sourceAccountRef: string;
  ownerUid: string;
  ownerName: string;
  productCount: number;
  mappedUserId: number | null;
  eligible: boolean;
}

export interface ExistingOwnerBinding {
  source_account_ref: string;
  owner_uid: string;
  app_user_id: number;
}

export async function loadOwnerBindingCandidates(): Promise<OwnerBindingCandidate[]> {
  const response = await backendRequest<Array<{
    source_account_ref: string;
    owner_uid: string;
    owner_name: string | null;
    product_count: number;
    mapped_user_id: number | null;
    eligible: boolean;
  }>>("/api/operations/logs/owner-mappings/candidates");
  return response.data.map((row) => ({
    sourceAccountRef: row.source_account_ref,
    ownerUid: row.owner_uid,
    ownerName: row.owner_name || "未命名",
    productCount: row.product_count,
    mappedUserId: row.mapped_user_id,
    eligible: row.eligible,
  }));
}

export async function loadExistingOwnerBindings(): Promise<ExistingOwnerBinding[]> {
  const response = await backendRequest<ExistingOwnerBinding[]>(
    "/api/operations/logs/owner-mappings",
  );
  return response.data;
}

export async function assignOwnerBinding(
  userId: string,
  item: OwnerBindingCandidate,
): Promise<void> {
  await backendRequest<{ saved: boolean; created: boolean }>(
    "/api/operations/logs/owner-mappings/assign",
    {
      method: "POST",
      body: JSON.stringify({
        source_account_ref: item.sourceAccountRef,
        owner_uid: item.ownerUid,
        app_user_id: Number(userId),
      }),
    },
  );
}

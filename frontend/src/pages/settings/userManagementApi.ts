import { backendRequest } from "@/api/backendApi";
import {
  fallbackUserRoleOptions,
  type FeishuDirectorySearchResult,
  type FeishuDirectoryUser,
  type UserFormValues,
  type UserManagementRow,
  type UserRoleName,
  type UserRoleOption,
} from "@/pages/settings/userManagementTypes";

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

interface BackendRole {
  id: string;
  role_key: string;
  name: string;
  description: string | null;
  is_system: boolean;
  user_count: number;
  permission_keys: string[];
}

const roleDisplayNameByKey: Record<string, string> = {
  admin: "管理员",
  operations: "运营",
  purchase: "采购",
  warehouse: "仓库",
  finance: "财务",
};

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

function toRoleOptions(roles: BackendRole[]): UserRoleOption[] {
  if (roles.length === 0) return fallbackUserRoleOptions;

  return roles.map((role) => ({
    key: role.role_key,
    name: roleDisplayNameByKey[role.role_key] ?? role.name,
  }));
}

function roleNameFromKey(roleKey: string, roleOptions: UserRoleOption[]): UserRoleName {
  return roleOptions.find((role) => role.key === roleKey)?.name
    ?? roleDisplayNameByKey[roleKey]
    ?? roleKey;
}

function roleKeysFromNames(names: UserRoleName[], roleOptions: UserRoleOption[]): string[] {
  return names.flatMap((name) => {
    const role = roleOptions.find((item) => item.name === name);
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
    roles: roleNames,
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
  const [usersResponse, rolesResponse] = await Promise.all([
    backendRequest<BackendUser[]>("/api/settings/users"),
    backendRequest<BackendRole[]>("/api/settings/roles"),
  ]);

  const roleOptions = toRoleOptions(rolesResponse.data);
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
): Promise<void> {
  await backendRequest<BackendUser>("/api/settings/users", {
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
      feishu_department_ids: values.feishuDepartmentIds?.length ? values.feishuDepartmentIds : undefined,
      role_keys: roleKeysFromNames(values.roles, roleOptions),
    }),
  });
}

export async function updateUser(
  userId: string,
  values: UserFormValues,
  roleOptions: UserRoleOption[],
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
      feishu_department_ids: values.feishuDepartmentIds?.length ? values.feishuDepartmentIds : undefined,
      is_active: values.status === "启用",
      role_keys: roleKeysFromNames(values.roles, roleOptions),
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

export async function deactivateUser(userId: string): Promise<void> {
  await backendRequest<BackendUser>(`/api/settings/users/${userId}`, {
    method: "DELETE",
  });
}

export type UserStatus = "启用" | "停用";

export type UserRoleName = string;

export interface FeishuDirectoryUser {
  name: string;
  openId: string;
  userId?: string;
  unionId?: string;
  employeeId?: string;
  departmentIds: string[];
}

export interface FeishuDirectorySearchResult {
  queryName: string;
  matchedCount: number;
  isUnique: boolean;
  users: FeishuDirectoryUser[];
}


export interface UserManagementRow {
  id: string;
  username: string;
  realName: string;
  phone: string;
  email: string;
  status: UserStatus;
  roles: UserRoleName[];
  feishuName?: string;
  feishuOpenId?: string;
  feishuUserId?: string;
  feishuUnionId?: string;
  feishuEmployeeId?: string;
  feishuDepartmentIds?: string[];
  createdAt: string;
  lastLoginAt: string;
}

export interface UserManagementFilters {
  status?: UserStatus;
  role?: UserRoleName;
  keyword: string;
}

export interface UserFormValues {
  username: string;
  realName: string;
  phone?: string;
  email?: string;
  password?: string;
  status: UserStatus;
  roles: UserRoleName[];
  feishuName?: string;
  feishuOpenId?: string;
  feishuUserId?: string;
  feishuUnionId?: string;
  feishuEmployeeId?: string;
  feishuDepartmentIds?: string[];
}

export interface UserManagementColumnField {
  key: string;
  title: string;
}

export interface UserRoleOption {
  key: string;
  name: UserRoleName;
}

export const userStatusOptions: UserStatus[] = ["启用", "停用"];

export const fallbackUserRoleOptions: UserRoleOption[] = [
  { key: "operations", name: "运营" },
  { key: "purchase", name: "采购" },
  { key: "warehouse", name: "仓库" },
  { key: "finance", name: "财务" },
  { key: "admin", name: "管理员" },
];

export const userRoleOptions: UserRoleName[] = fallbackUserRoleOptions.map((role) => role.name);

export const userManagementColumnFields: UserManagementColumnField[] = [
  { key: "username", title: "用户名" },
  { key: "realName", title: "真实姓名" },
  { key: "phone", title: "手机号" },
  { key: "email", title: "邮箱" },
  { key: "status", title: "状态" },
  { key: "roles", title: "角色" },
  { key: "createdAt", title: "创建时间" },
  { key: "lastLoginAt", title: "最近登录" },
  { key: "operation", title: "操作" },
];

export const defaultUserColumnWidths: Record<string, number> = {
  username: 168,
  realName: 132,
  phone: 132,
  email: 180,
  status: 92,
  roles: 240,
  createdAt: 156,
  lastLoginAt: 156,
  operation: 292,
};

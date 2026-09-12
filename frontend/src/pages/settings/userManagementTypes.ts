export type UserStatus = "启用" | "停用";

export type UserRoleName = "AI助手" | "运营" | "采购" | "仓库管理" | "财务管理" | "管理员";

export interface UserManagementRow {
  id: string;
  username: string;
  realName: string;
  phone: string;
  email: string;
  status: UserStatus;
  roles: UserRoleName[];
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
  status: UserStatus;
  roles: UserRoleName[];
}

export interface UserManagementColumnField {
  key: string;
  title: string;
}

export const userStatusOptions: UserStatus[] = ["启用", "停用"];

export const userRoleOptions: UserRoleName[] = [
  "AI助手",
  "运营",
  "采购",
  "仓库管理",
  "财务管理",
  "管理员",
];

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

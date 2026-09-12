export type PermissionTabKey = "pages" | "actions" | "fields";

export type FieldPermissionValue = "visible" | "hidden" | "adminOnly";

export interface RoleManagementRow {
  id: string;
  name: string;
  description: string;
  preset: boolean;
  userCount: number;
}

export interface PermissionGroup {
  title: string;
  items: string[];
}

export interface RolePermissionState {
  pagePermissions: Record<string, boolean>;
  actionPermissions: Record<string, boolean>;
  fieldPermissions: Record<string, FieldPermissionValue>;
}

export interface RoleFormValues {
  name: string;
  description?: string;
}

export const permissionTabs: { key: PermissionTabKey; label: string }[] = [
  { key: "pages", label: "页面权限" },
  { key: "actions", label: "功能权限" },
  { key: "fields", label: "字段权限" },
];

export const fieldPermissionOptions: { label: string; value: FieldPermissionValue }[] = [
  { label: "可见", value: "visible" },
  { label: "不可见", value: "hidden" },
  { label: "仅管理员可见", value: "adminOnly" },
];

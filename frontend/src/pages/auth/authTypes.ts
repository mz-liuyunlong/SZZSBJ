export type ClientUserRole = "admin" | "user";

export interface BackendUser {
  id: number;
  username: string;
  display_name: string | null;
  phone: string | null;
  email: string | null;
  is_active: boolean;
  is_super_admin: boolean;
  role_keys: string[];
  role_names: string[];
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

export interface BackendCurrentUser extends BackendUser {
  permissions: string[];
}

export interface AuthUser {
  id: number;
  username: string;
  role: ClientUserRole;
  displayName: string;
  account: string;
  avatarSrc: string;
  online: boolean;
  roleKeys: string[];
  roles: string[];
  permissions: string[];
  isSuperAdmin: boolean;
}

export const DEFAULT_AUTH_USER: AuthUser = {
  id: 0,
  username: "admin",
  role: "admin",
  displayName: "管理员",
  account: "admin",
  avatarSrc: "/default-avatar.png",
  online: true,
  roleKeys: ["admin"],
  roles: ["超级管理员"],
  permissions: ["*"],
  isSuperAdmin: true,
};

export function toAuthUser(user: BackendUser | BackendCurrentUser): AuthUser {
  const permissions = "permissions" in user ? user.permissions : [];
  const isSuperAdmin = user.is_super_admin || permissions.includes("*");

  return {
    id: user.id,
    username: user.username,
    role: isSuperAdmin ? "admin" : "user",
    displayName: user.display_name || user.username,
    account: user.email || user.username,
    avatarSrc: "/default-avatar.png",
    online: true,
    roleKeys: user.role_keys,
    roles: isSuperAdmin
      ? ["超级管理员", ...user.role_names.filter((name) => name !== "管理员")]
      : user.role_names,
    permissions,
    isSuperAdmin,
  };
}

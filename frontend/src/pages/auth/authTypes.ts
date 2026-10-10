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
  roles: ["管理员"],
  permissions: ["*"],
};

export function toAuthUser(user: BackendUser | BackendCurrentUser): AuthUser {
  const permissions = "permissions" in user ? user.permissions : [];
  const isAdmin = user.is_super_admin || user.role_keys.includes("admin");

  return {
    id: user.id,
    username: user.username,
    role: isAdmin ? "admin" : "user",
    displayName: user.display_name || user.username,
    account: user.email || user.username,
    avatarSrc: "/default-avatar.png",
    online: true,
    roleKeys: user.role_keys,
    roles: user.role_names,
    permissions,
  };
}

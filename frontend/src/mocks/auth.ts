/** Public frontend-only credentials for UI verification; these are not secrets or real authentication. */
export type MockUserRole = "admin" | "user";

export interface MockAuthUser {
  username: string;
  role: MockUserRole;
  displayName: string;
  account: string;
  avatarSrc: string;
  online: boolean;
}

export const MOCK_USERNAME = "user";
export const MOCK_USER_USERNAME = "user";
export const MOCK_PASSWORD = "12345678";

export const MOCK_USERS: MockAuthUser[] = [
  {
    username: "admin",
    role: "admin",
    displayName: "管理员",
    account: "admin@example.local",
    avatarSrc: "/default-avatar.png",
    online: true,
  },
  {
    username: "user",
    role: "user",
    displayName: "普通用户",
    account: "user@example.local",
    avatarSrc: "/default-avatar.png",
    online: true,
  },
];

export const DEFAULT_MOCK_AUTH_USER = MOCK_USERS[0];

export const findMockUser = (username: string) =>
  MOCK_USERS.find((user) => user.username === username.trim());

export const authenticateMockLogin = (username: string, password: string) => {
  if (password !== MOCK_PASSWORD) return undefined;
  return findMockUser(username);
};

export const isValidMockLogin = (username: string, password: string) =>
  Boolean(authenticateMockLogin(username, password));

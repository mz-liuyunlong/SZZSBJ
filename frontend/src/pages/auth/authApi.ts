import { BackendRequestError, backendRequest } from "@/api/backendApi";
import {
  clearAuthToken,
  clearAuthTokenIfCurrent,
  readAuthToken,
  writeAuthToken,
} from "@/pages/auth/authSession";
import { toAuthUser, type AuthUser, type BackendCurrentUser, type BackendUser } from "@/pages/auth/authTypes";

interface LoginPayload {
  username: string;
  password: string;
}

interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: BackendUser;
}

export async function loginWithPassword(payload: LoginPayload): Promise<AuthUser> {
  const response = await backendRequest<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  writeAuthToken(response.data.access_token);

  try {
    const currentUserResponse = await backendRequest<BackendCurrentUser>("/api/auth/me");
    return toAuthUser(currentUserResponse.data);
  } catch (error) {
    if (isAuthenticationFailure(error)) {
      clearAuthTokenIfCurrent(response.data.access_token);
    }
    throw error;
  }
}

export async function fetchCurrentUser(): Promise<AuthUser | undefined> {
  const token = readAuthToken();
  if (!token) return undefined;

  try {
    const response = await backendRequest<BackendCurrentUser>("/api/auth/me");
    return toAuthUser(response.data);
  } catch (error) {
    if (isAuthenticationFailure(error)) {
      clearAuthTokenIfCurrent(token);
      return undefined;
    }
    throw error;
  }
}

export function isAuthenticationFailure(error: unknown): boolean {
  return error instanceof BackendRequestError
    && (error.status === 401 || error.code === "UNAUTHORIZED");
}

export function loginErrorMessage(error: unknown): string {
  if (!(error instanceof BackendRequestError)) return "登录失败，请稍后重试";
  if (error.status === 401) return "账号或密码错误";
  if (error.status === 403) return "账号已停用，请联系管理员";
  if (error.kind === "timeout") return "请求超时，请重试";
  if (error.kind === "network") return "网络连接失败，请检查网络";
  if (error.kind === "gateway" || error.kind === "server") {
    return "系统连接暂时异常，请稍后重试";
  }
  return "登录失败，请稍后重试";
}

export function sessionRestoreErrorMessage(error: unknown): string {
  if (error instanceof BackendRequestError && error.status === 403) {
    return "当前账号无权访问，请联系管理员。登录状态已保留。";
  }
  if (error instanceof BackendRequestError && error.kind === "network") {
    return "网络连接失败，已保留本地登录状态。请检查网络后重试。";
  }
  if (error instanceof BackendRequestError && error.kind === "timeout") {
    return "认证请求超时，已保留本地登录状态。请稍后重试。";
  }
  return "认证服务连接异常，已保留本地登录状态。请稍后重试。";
}

export async function logoutCurrentUser(): Promise<void> {
  if (!readAuthToken()) return;

  try {
    await backendRequest<{ revoked: boolean }>("/api/auth/logout", { method: "POST" });
  } finally {
    clearAuthToken();
  }
}


export interface PasswordResetRequestPayload {
  realName: string;
}

export interface PasswordResetConfirmPayload {
  token: string;
  newPassword: string;
}

export interface PasswordResetMessage {
  message: string;
}

export async function requestPasswordReset(
  payload: PasswordResetRequestPayload,
): Promise<PasswordResetMessage> {
  const response = await backendRequest<PasswordResetMessage>(
    "/api/auth/password-reset/request",
    {
      method: "POST",
      body: JSON.stringify({
        real_name: payload.realName,
      }),
    },
  );

  return response.data;
}

export async function confirmPasswordReset(
  payload: PasswordResetConfirmPayload,
): Promise<PasswordResetMessage> {
  const response = await backendRequest<PasswordResetMessage>(
    "/api/auth/password-reset/confirm",
    {
      method: "POST",
      body: JSON.stringify({
        token: payload.token,
        new_password: payload.newPassword,
      }),
    },
  );

  return response.data;
}

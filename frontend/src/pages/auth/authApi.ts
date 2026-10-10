import { backendRequest } from "@/api/backendApi";
import { clearAuthToken, readAuthToken, writeAuthToken } from "@/pages/auth/authSession";
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
  return toAuthUser(response.data.user);
}

export async function fetchCurrentUser(): Promise<AuthUser | undefined> {
  if (!readAuthToken()) return undefined;

  try {
    const response = await backendRequest<BackendCurrentUser>("/api/auth/me");
    return toAuthUser(response.data);
  } catch {
    clearAuthToken();
    return undefined;
  }
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

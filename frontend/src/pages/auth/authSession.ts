export const AUTH_TOKEN_STORAGE_KEY = "szzsbj_auth_token";
const AUTH_SESSION_CHANNEL = "szzsbj_auth_session";

type AuthSessionEvent = "token-changed" | "logged-out";

function publishAuthSessionEvent(event: AuthSessionEvent): void {
  if (typeof BroadcastChannel === "undefined") return;
  const channel = new BroadcastChannel(AUTH_SESSION_CHANNEL);
  channel.postMessage(event);
  channel.close();
}

export function readAuthToken(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function writeAuthToken(token: string): void {
  try {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
    publishAuthSessionEvent("token-changed");
  } catch {
    // Ignore storage failures; the current login response can still update memory state.
  }
}

export function clearAuthToken(): void {
  try {
    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    publishAuthSessionEvent("logged-out");
  } catch {
    // Ignore storage failures during logout cleanup.
  }
}

export function clearAuthTokenIfCurrent(expectedToken: string): boolean {
  if (readAuthToken() !== expectedToken) return false;
  clearAuthToken();
  return true;
}

export function subscribeAuthSession(
  listener: (event: AuthSessionEvent) => void,
): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key !== AUTH_TOKEN_STORAGE_KEY) return;
    listener(event.newValue ? "token-changed" : "logged-out");
  };
  window.addEventListener("storage", onStorage);

  const channel = typeof BroadcastChannel === "undefined"
    ? undefined
    : new BroadcastChannel(AUTH_SESSION_CHANNEL);
  const onMessage = (event: MessageEvent<AuthSessionEvent>) => listener(event.data);
  channel?.addEventListener("message", onMessage);

  return () => {
    window.removeEventListener("storage", onStorage);
    channel?.removeEventListener("message", onMessage);
    channel?.close();
  };
}

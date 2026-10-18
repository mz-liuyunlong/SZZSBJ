export const AUTH_TOKEN_STORAGE_KEY = "szzsbj_auth_token";
const AUTH_SESSION_CHANNEL = "szzsbj_auth_session";

export type AuthSessionEvent = {
  type: "token-changed" | "logged-out";
  token: string;
};

let observedAuthToken: string | null | undefined;

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
    observedAuthToken = token;
    publishAuthSessionEvent({ type: "token-changed", token });
  } catch {
    // Ignore storage failures; the current login response can still update memory state.
  }
}

export function clearAuthToken(): void {
  const token = readAuthToken();
  if (!token) return;
  try {
    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    observedAuthToken = null;
    publishAuthSessionEvent({ type: "logged-out", token });
  } catch {
    // Ignore storage failures during logout cleanup.
  }
}

export function clearAuthTokenIfCurrent(expectedToken: string): boolean {
  if (readAuthToken() !== expectedToken) return false;
  try {
    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    observedAuthToken = null;
    publishAuthSessionEvent({ type: "logged-out", token: expectedToken });
  } catch {
    // Ignore storage failures during logout cleanup.
  }
  return true;
}

export function isCurrentAuthSessionEvent(event: AuthSessionEvent): boolean {
  const currentToken = readAuthToken();
  const previousToken = observedAuthToken === undefined ? currentToken : observedAuthToken;
  if (event.type === "token-changed") {
    if (currentToken !== event.token || previousToken === event.token) return false;
    observedAuthToken = event.token;
    return true;
  }
  if (currentToken !== null || previousToken !== event.token) return false;
  observedAuthToken = null;
  return true;
}

export function subscribeAuthSession(
  listener: (event: AuthSessionEvent) => void,
): () => void {
  if (observedAuthToken === undefined) observedAuthToken = readAuthToken();
  const onStorage = (event: StorageEvent) => {
    if (event.key !== AUTH_TOKEN_STORAGE_KEY) return;
    if (event.newValue) {
      listener({ type: "token-changed", token: event.newValue });
    } else if (event.oldValue) {
      listener({ type: "logged-out", token: event.oldValue });
    }
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

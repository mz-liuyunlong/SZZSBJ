const STORAGE_PREFIX = "szzsbj:user-preference";

interface StoredPreference<T> {
  version: number;
  value: T;
}

const storageKey = (scope: string, key: string) => (
  `${STORAGE_PREFIX}:${encodeURIComponent(scope)}:${encodeURIComponent(key)}`
);

export function readUserPreference<T>(
  scope: string,
  key: string,
  version: number,
): T | undefined {
  if (typeof window === "undefined") return undefined;

  try {
    const raw = window.localStorage.getItem(storageKey(scope, key));
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as StoredPreference<T>;
    return parsed.version === version ? parsed.value : undefined;
  } catch {
    return undefined;
  }
}

export function writeUserPreference<T>(
  scope: string,
  key: string,
  version: number,
  value: T,
) {
  if (typeof window === "undefined") return;

  try {
    const payload: StoredPreference<T> = { version, value };
    window.localStorage.setItem(storageKey(scope, key), JSON.stringify(payload));
  } catch {
    // Browser storage is only a fast local preference cache; the backend remains source of truth.
  }
}

export function removeUserPreference(scope: string, key: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(storageKey(scope, key));
  } catch {
    // Ignore unavailable browser storage.
  }
}

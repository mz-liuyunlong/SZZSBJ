import {
  useCallback,
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";

const pageStateCache = new Map<string, unknown>();
const storagePrefix = "szzsbj:page-state:";

const resolveInitialState = <T>(initialState: T | (() => T)): T => (
  typeof initialState === "function"
    ? (initialState as () => T)()
    : initialState
);

const storageKey = (cacheKey: string) => `${storagePrefix}${cacheKey}`;

const readSessionState = <T>(cacheKey: string): T | undefined => {
  if (typeof window === "undefined") return undefined;

  try {
    const value = window.sessionStorage.getItem(storageKey(cacheKey));
    return value === null ? undefined : JSON.parse(value) as T;
  } catch {
    return undefined;
  }
};

const writeSessionState = <T>(cacheKey: string, value: T) => {
  if (typeof window === "undefined") return;

  try {
    const serialized = JSON.stringify(value);
    if (serialized === undefined) {
      window.sessionStorage.removeItem(storageKey(cacheKey));
      return;
    }
    window.sessionStorage.setItem(storageKey(cacheKey), serialized);
  } catch {
    // sessionStorage may be unavailable or quota-limited. In-memory cache still works.
  }
};

const removeSessionState = (cacheKey: string) => {
  if (typeof window === "undefined") return;

  try {
    window.sessionStorage.removeItem(storageKey(cacheKey));
  } catch {
    // Ignore storage cleanup failures.
  }
};

const clearSessionState = () => {
  if (typeof window === "undefined") return;

  try {
    for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = window.sessionStorage.key(index);
      if (key?.startsWith(storagePrefix)) {
        window.sessionStorage.removeItem(key);
      }
    }
  } catch {
    // Ignore storage cleanup failures.
  }
};

export function readPageStateCache<T>(cacheKey: string) {
  if (pageStateCache.has(cacheKey)) {
    return pageStateCache.get(cacheKey) as T;
  }

  const sessionState = readSessionState<T>(cacheKey);
  if (sessionState !== undefined) {
    pageStateCache.set(cacheKey, sessionState);
  }
  return sessionState;
}

export function writePageStateCache<T>(cacheKey: string, value: T) {
  pageStateCache.set(cacheKey, value);
  writeSessionState(cacheKey, value);
}

export function removePageStateCache(cacheKey: string) {
  pageStateCache.delete(cacheKey);
  removeSessionState(cacheKey);
}

export function clearPageStateCache() {
  pageStateCache.clear();
  clearSessionState();
}

export function usePageStateCache<T>(
  cacheKey: string,
  initialState: T | (() => T),
): readonly [T, Dispatch<SetStateAction<T>>, () => void] {
  const [state, setState] = useState<T>(() => {
    const cachedState = readPageStateCache<T>(cacheKey);
    if (cachedState !== undefined) return cachedState;

    const nextState = resolveInitialState(initialState);
    writePageStateCache(cacheKey, nextState);
    return nextState;
  });

  const setCachedState: Dispatch<SetStateAction<T>> = (value) => {
    setState((currentState) => {
      const nextState = typeof value === "function"
        ? (value as (previousState: T) => T)(currentState)
        : value;
      writePageStateCache(cacheKey, nextState);
      return nextState;
    });
  };

  useEffect(() => {
    writePageStateCache(cacheKey, state);
  }, [cacheKey, state]);

  const resetState = useCallback(() => {
    const nextState = resolveInitialState(initialState);
    writePageStateCache(cacheKey, nextState);
    setState(nextState);
  }, [cacheKey, initialState]);

  return [state, setCachedState, resetState] as const;
}

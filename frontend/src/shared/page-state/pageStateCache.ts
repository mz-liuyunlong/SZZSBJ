import {
  useCallback,
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";

const pageStateCache = new Map<string, unknown>();

const resolveInitialState = <T>(initialState: T | (() => T)): T => (
  typeof initialState === "function"
    ? (initialState as () => T)()
    : initialState
);

export function readPageStateCache<T>(cacheKey: string) {
  return pageStateCache.get(cacheKey) as T | undefined;
}

export function writePageStateCache<T>(cacheKey: string, value: T) {
  pageStateCache.set(cacheKey, value);
}

export function removePageStateCache(cacheKey: string) {
  pageStateCache.delete(cacheKey);
}

export function clearPageStateCache() {
  pageStateCache.clear();
}

export function usePageStateCache<T>(
  cacheKey: string,
  initialState: T | (() => T),
): readonly [T, Dispatch<SetStateAction<T>>, () => void] {
  const [state, setState] = useState<T>(() => {
    if (pageStateCache.has(cacheKey)) {
      return pageStateCache.get(cacheKey) as T;
    }
    return resolveInitialState(initialState);
  });

  useEffect(() => {
    pageStateCache.set(cacheKey, state);
  }, [cacheKey, state]);

  const resetState = useCallback(() => {
    const nextState = resolveInitialState(initialState);
    pageStateCache.set(cacheKey, nextState);
    setState(nextState);
  }, [cacheKey, initialState]);

  return [state, setState, resetState] as const;
}

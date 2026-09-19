import { runWithoutBackendRequestBusy } from "@/shared/network/backendRequestBusy";
/**
 * Small in-memory resource cache for report pages.
 *
 * Goals:
 * - dedupe in-flight requests
 * - reuse recently loaded API results when switching tabs/pages
 * - allow safe idle preloading without blocking navigation
 */
interface ResourceCacheEntry<T> {
  value?: T;
  promise?: Promise<T>;
  updatedAt: number;
}

interface ResourceCacheOptions {
  staleTimeMs?: number;
}

const DEFAULT_STALE_TIME_MS = 5 * 60 * 1000;
const resourceCache = new Map<string, ResourceCacheEntry<unknown>>();

const now = () => Date.now();

export const stableCacheKey = (value: unknown): string => {
  if (value == null) return String(value);
  if (Array.isArray(value)) return `[${value.map(stableCacheKey).join(",")}]`;
  if (typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${stableCacheKey(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
};

export function getCachedResource<T>(
  key: string,
  loader: () => Promise<T>,
  options: ResourceCacheOptions = {},
): Promise<T> {
  const staleTimeMs = options.staleTimeMs ?? DEFAULT_STALE_TIME_MS;
  const current = resourceCache.get(key) as ResourceCacheEntry<T> | undefined;

  if (current?.value !== undefined && now() - current.updatedAt < staleTimeMs) {
    return Promise.resolve(current.value);
  }

  if (current?.promise) {
    return current.promise;
  }

  const promise = loader()
    .then((value) => {
      resourceCache.set(key, {
        value,
        updatedAt: now(),
      });
      return value;
    })
    .catch((error) => {
      resourceCache.delete(key);
      throw error;
    });

  resourceCache.set(key, {
    promise,
    updatedAt: current?.updatedAt ?? now(),
    value: current?.value,
  });

  return promise;
}

export function preloadCachedResource<T>(
  key: string,
  loader: () => Promise<T>,
  options: ResourceCacheOptions = {},
) {
  runWithoutBackendRequestBusy(() => {
    void getCachedResource(key, loader, options).catch(() => undefined);
  });
}

export function clearResourceCache(prefix?: string) {
  if (!prefix) {
    resourceCache.clear();
    return;
  }

  for (const key of resourceCache.keys()) {
    if (key.startsWith(prefix)) resourceCache.delete(key);
  }
}

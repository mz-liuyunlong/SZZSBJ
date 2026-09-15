import { QueryClient } from "@tanstack/react-query";

export const SERVER_STATE_STALE_TIME = {
  realtime: 0,
  fast: 15_000,
  list: 45_000,
  summary: 45_000,
  detail: 3 * 60_000,
  options: 15 * 60_000,
  preferences: 30 * 60_000,
} as const;

export const SERVER_STATE_GC_TIME = 30 * 60_000;

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 0,
      gcTime: SERVER_STATE_GC_TIME,
      retry: 1,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
    },
    mutations: {
      retry: 0,
    },
  },
});

export function clearServerState() {
  queryClient.clear();
}

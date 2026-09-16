import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { SERVER_STATE_STALE_TIME } from "@/api/queryClient";
import {
  listIntegrationSyncRunRawRequestRefs,
  listIntegrationSyncRunWorkItems,
  listIntegrationSyncTasks,
} from "@/pages/data-center/integrationSyncTaskApi";

const emptyRunId = "__none__";

export const integrationSyncTaskKeys = {
  all: ["integration-sync-tasks"] as const,
  overview: ["integration-sync-tasks", "overview"] as const,
  run: (runId: string) => ["integration-sync-tasks", "run", runId] as const,
  workItems: (runId: string) => [
    "integration-sync-tasks",
    "run",
    runId,
    "work-items",
  ] as const,
  rawRequestRefs: (runId: string) => [
    "integration-sync-tasks",
    "run",
    runId,
    "raw-request-refs",
  ] as const,
};

export function useIntegrationSyncTasksQuery() {
  return useQuery({
    queryKey: integrationSyncTaskKeys.overview,
    queryFn: listIntegrationSyncTasks,
    staleTime: SERVER_STATE_STALE_TIME.list,
    placeholderData: keepPreviousData,
  });
}

export function useIntegrationSyncRunWorkItemsQuery(
  runId?: string,
  enabled = true,
) {
  return useQuery({
    queryKey: integrationSyncTaskKeys.workItems(runId ?? emptyRunId),
    queryFn: () => {
      if (!runId) throw new Error("SYNC_RUN_ID_REQUIRED");
      return listIntegrationSyncRunWorkItems(runId);
    },
    enabled: Boolean(runId) && enabled,
    staleTime: SERVER_STATE_STALE_TIME.detail,
  });
}

export function useIntegrationSyncRunRawRequestRefsQuery(
  runId?: string,
  enabled = true,
) {
  return useQuery({
    queryKey: integrationSyncTaskKeys.rawRequestRefs(runId ?? emptyRunId),
    queryFn: () => {
      if (!runId) throw new Error("SYNC_RUN_ID_REQUIRED");
      return listIntegrationSyncRunRawRequestRefs(runId);
    },
    enabled: Boolean(runId) && enabled,
    staleTime: SERVER_STATE_STALE_TIME.detail,
  });
}

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SERVER_STATE_STALE_TIME } from "@/api/queryClient";
import {
  createIntegrationSyncManualRun,
  listIntegrationSyncRunRawRequestRefs,
  listIntegrationSyncRunWorkItems,
  listIntegrationSyncTasks,
  retryIntegrationSyncRun,
  updateIntegrationSyncConfig,
  type SyncConfigUpdatePayload,
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

export function useCreateIntegrationSyncManualRunMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ configId, reason }: { configId: string; reason: string }) => (
      createIntegrationSyncManualRun(configId, reason)
    ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: integrationSyncTaskKeys.overview });
    },
  });
}

export function useRetryIntegrationSyncRunMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, reason }: { runId: string; reason: string }) => (
      retryIntegrationSyncRun(runId, reason)
    ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: integrationSyncTaskKeys.overview });
    },
  });
}

export function useUpdateIntegrationSyncConfigMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      configId,
      payload,
    }: {
      configId: string;
      payload: SyncConfigUpdatePayload;
    }) => updateIntegrationSyncConfig(configId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: integrationSyncTaskKeys.overview });
    },
  });
}

/** Query keys include the authenticated user; refresh invalidates both sides of the handoff. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listPending, pendingOptions, pendingSummary } from "./pendingPackingApi";
import type { PendingFilters } from "./pendingPackingTypes";
export function usePendingPacking(filters: PendingFilters, page: number, size: number, scope: string) {
  const client = useQueryClient();
  const base = ["wfs-pending-packing", scope];
  const list = useQuery({ queryKey: [...base, "orders", filters, page, size], queryFn: ({ signal }) => listPending(filters, page, size, signal), retry: false });
  const summary = useQuery({ queryKey: [...base, "summary", filters], queryFn: ({ signal }) => pendingSummary(filters, signal), retry: false });
  const options = useQuery({ queryKey: [...base, "options"], queryFn: ({ signal }) => pendingOptions(signal), retry: false });
  const refresh = async () => {
    await Promise.all([client.invalidateQueries({ queryKey: base }), client.invalidateQueries({ queryKey: ["domestic-packing-warehouse"] }), client.invalidateQueries({ queryKey: ["domestic-packing-approval"] })]);
  };
  return { list, summary, options, refresh };
}

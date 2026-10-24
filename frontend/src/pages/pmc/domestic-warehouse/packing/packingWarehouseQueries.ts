/** Warehouse queries are isolated by user scope; writes refresh only domestic packing. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCurrentUser } from "@/pages/auth/authApi";
import { getWarehouseOptions, getWarehouseSummary, listWarehouseOrders, writeWarehouseOrder } from "./packingWarehouseApi";
import type { PackingWarehouseFilters, WarehouseAction, WarehouseBase, WarehouseFields } from "./packingWarehouseTypes";
export function usePackingWarehouse(filters: PackingWarehouseFilters, page: number, size: number, scope: string) {
  const client = useQueryClient(); const base = ["domestic-packing-warehouse", scope];
  const list = useQuery({ queryKey: [...base, "orders", filters, page, size], queryFn: ({ signal }) => listWarehouseOrders(filters, page, size, signal) });
  const summary = useQuery({ queryKey: [...base, "summary", filters], queryFn: ({ signal }) => getWarehouseSummary(filters, signal) });
  const options = useQuery({ queryKey: [...base, "options"], queryFn: ({ signal }) => getWarehouseOptions(signal) });
  const user = useQuery({ queryKey: ["packing-warehouse-user", scope], queryFn: fetchCurrentUser, staleTime: 30000 });
  const write = useMutation({ mutationFn: ({ id, action, body }: { id: string; action: WarehouseAction; body: WarehouseBase & WarehouseFields }) => writeWarehouseOrder(id, action, body), onSuccess: async () => { await client.invalidateQueries({ queryKey: base }); await client.invalidateQueries({ queryKey: ["domestic-packing-approval", scope] }); await client.invalidateQueries({ queryKey: ["domestic-packing-risk", scope] }); } });
  return { list, summary, options, user, write, refresh: () => client.invalidateQueries({ queryKey: base }) };
}

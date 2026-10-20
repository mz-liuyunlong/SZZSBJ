/** User-scoped queries; successful decisions invalidate all packing projections. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCurrentUser } from "@/pages/auth/authApi";
import { decidePacking, getApprovalOptions, getApprovalSummary, listApprovalCandidates, listPackingOrders, type DecisionKind, type DecisionPayload } from "./packingApprovalApi";
import type { PackingApprovalFilters } from "./packingApprovalTypes";
export function usePackingApproval(f: PackingApprovalFilters, page: number, size: number, scope: string, historyOpen: boolean, historyPage: number) {
  const client = useQueryClient(); const base = ["domestic-packing-approval", scope];
  const list = useQuery({ queryKey: [...base, "pending", f, page, size], queryFn: ({ signal }) => listApprovalCandidates(f, page, size, signal) });
  const summary = useQuery({ queryKey: [...base, "summary", f], queryFn: ({ signal }) => getApprovalSummary(f, signal) });
  const options = useQuery({ queryKey: [...base, "options"], queryFn: ({ signal }) => getApprovalOptions(signal) });
  const history = useQuery({ queryKey: [...base, "orders", f, historyPage], queryFn: ({ signal }) => listPackingOrders(f, historyPage, signal), enabled: historyOpen });
  const user = useQuery({ queryKey: ["packing-approval-user", scope], queryFn: fetchCurrentUser, staleTime: 30_000 });
  const decision = useMutation({ mutationFn: ({ id, kind, body }: { id: string; kind: DecisionKind; body: DecisionPayload }) => decidePacking(id, kind, body), onSuccess: () => client.invalidateQueries({ queryKey: base }) });
  return { list, summary, options, history, user, decision, refresh: () => client.invalidateQueries({ queryKey: base }) };
}

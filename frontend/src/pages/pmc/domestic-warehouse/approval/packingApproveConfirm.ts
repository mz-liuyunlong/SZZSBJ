/** Shared approval confirmation copy and the existing operator options. */
import type { ApprovalCandidate } from "./packingApprovalApi";

export const DOMESTIC_APPROVER_NAMES = ["吴贤玲"];

function dash(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

export function approveConfirmTitle(row: ApprovalCandidate) {
  const pk = row.pk?.trim();
  return pk ? `审批通过 · ${pk} · ${row.sku}` : `审批通过 · ${row.sku}`;
}

export function approveConfirmSummary(row: ApprovalCandidate) {
  return `入库单 ${row.inbound_order_sn} · ItemID ${dash(row.item_id)} · GTIN ${dash(row.gtin)} · MSKU ${dash(row.msku)}`;
}

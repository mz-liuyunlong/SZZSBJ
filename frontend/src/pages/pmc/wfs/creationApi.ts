import { backendDownload, backendRequest } from "@/api/backendApi";
import { pendingPrefix } from "./pendingPackingApi";
import type { ReturnAddress } from "./pendingPackingTypes";

export interface AllocationInput {
  order_id: string; expected_version: number; expected_box_version: number;
  additional_selections?: { order_id: string; expected_version: number; expected_box_version: number }[];
  shipping_boxes: number; shipment_count: number; shipment_boxes: number[];
}
export interface BoxRange {
  order_id: string; pk: string; sku: string; box_version: number;
  line_id: string; line_no: number; start: number; end: number; boxes: number;
  units_per_box: number; units: number; length_cm: string; width_cm: string;
  height_cm: string; gross_weight_kg: string;
}
export interface AllocationTicket { number: number; boxes: number; units: number; ranges: BoxRange[] }
export interface AllocationPreview {
  order_id: string; order_version: number; box_version: number;
  available_boxes: number; remaining_boxes: number; tickets: AllocationTicket[]; preview_hash: string;
}
export interface CreationInput extends AllocationInput {
  source_account_ref: string; preview_hash: string; idempotency_key: string;
  return_address?: ReturnAddress; its: boolean; expected_delivery_at?: string;
}
export type CreationState = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "UNKNOWN" | "PARTIAL";
export interface CreationOperation {
  id: string; order_id: string; state: CreationState; created_at: string;
  approval_mode: "automatic"; automatically_approved_at: string | null;
  tickets: { id: string; number: number; state: CreationState; allocation: AllocationTicket;
    error_code: string | null; shipments: { shipment_id: string; label_state: "PENDING" | "READY" | "FAILED" }[] }[];
}
export const creationLabels: Record<CreationState, string> = {
  QUEUED: "待执行", RUNNING: "创建中", SUCCEEDED: "创建成功", FAILED: "创建失败", UNKNOWN: "结果待确认", PARTIAL: "部分成功",
};
export const getCreationCapabilities = (signal?: AbortSignal) => backendRequest<{ creation_enabled: boolean; preview_enabled: boolean; reason: string | null }>(`${pendingPrefix}/capabilities`, { signal });
export const allocationPreview = (body: AllocationInput) => backendRequest<AllocationPreview>(`${pendingPrefix}/allocation-preview`, { method: "POST", body: JSON.stringify(body) });
export const createShipments = (body: CreationInput) => backendRequest<CreationOperation>(`${pendingPrefix}/creation-operations`, { method: "POST", body: JSON.stringify(body) });
export const listCreationOperations = (id: string, page = 1, signal?: AbortSignal) => backendRequest<{ items: CreationOperation[]; total: number }>(`${pendingPrefix}/creation-operations?order_id=${encodeURIComponent(id)}&page=${page}&page_size=10`, { signal });
export const recoverCreation = (id: string, action: "reconcile" | "labels/retry") => backendRequest<CreationOperation>(`${pendingPrefix}/creation-operations/${encodeURIComponent(id)}/${action}`, { method: "POST" });
export const optionalPreview = (body: CreationInput) => backendRequest<{ preview_hash: string; result: unknown }>(`${pendingPrefix}/optional-previews`, { method: "POST", body: JSON.stringify(body) });
export const downloadCreationLabel = (id: string, shipmentId: string) => backendDownload(`${pendingPrefix}/creation-operations/${encodeURIComponent(id)}/labels/${encodeURIComponent(shipmentId)}`, "wfs-label.pdf");

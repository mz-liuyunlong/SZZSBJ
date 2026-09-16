import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { SERVER_STATE_STALE_TIME } from "@/api/queryClient";
import {
  getProductManagementOptions,
  getProductManagementSku,
  getProductManagementSummary,
  getProductManagementTableView,
  listProductManagementSkus,
  saveProductManagementTableView,
} from "@/pages/products/productManagementApi";
import type { ProductManagementFilters, ProductManagementRow } from "@/pages/products/productManagementTypes";

const baseFilterKey = (filters: ProductManagementFilters) => ({
  ownerUid: filters.ownerUid ?? null,
  developerUid: filters.developerUid ?? null,
  tag: filters.tag ?? null,
  productGrade: filters.productGrade ?? null,
  keyword: filters.keyword.trim(),
  batchValues: filters.batchValues ?? [],
});

const listFilterKey = (filters: ProductManagementFilters) => ({
  ...baseFilterKey(filters),
  issueCode: filters.issueCode ?? null,
});

export const productManagementKeys = {
  all: ["product-management"] as const,
  list: (filters: ProductManagementFilters, page: number, pageSize: number) => (
    ["product-management", "list", listFilterKey(filters), page, pageSize] as const
  ),
  summary: (filters: ProductManagementFilters) => (
    ["product-management", "summary", baseFilterKey(filters)] as const
  ),
  options: (filters: ProductManagementFilters) => (["product-management", "options", baseFilterKey(filters)] as const),
  detail: (skuId: string) => ["product-management", "detail", skuId] as const,
  tableView: ["product-management", "table-view", "default"] as const,
};

export function useProductManagementListQuery(
  filters: ProductManagementFilters,
  page: number,
  pageSize: number,
) {
  return useQuery({
    queryKey: productManagementKeys.list(filters, page, pageSize),
    queryFn: () => listProductManagementSkus(filters, page, pageSize),
    staleTime: SERVER_STATE_STALE_TIME.list,
    placeholderData: keepPreviousData,
  });
}

export function usePrefetchProductManagementList() {
  const queryClient = useQueryClient();
  return useCallback((
    filters: ProductManagementFilters,
    page: number,
    pageSize: number,
  ) => queryClient.prefetchQuery({
    queryKey: productManagementKeys.list(filters, page, pageSize),
    queryFn: () => listProductManagementSkus(filters, page, pageSize),
    staleTime: SERVER_STATE_STALE_TIME.list,
  }), [queryClient]);
}

export function useProductManagementSummaryQuery(
  filters: ProductManagementFilters,
  enabled: boolean,
) {
  return useQuery({
    queryKey: productManagementKeys.summary(filters),
    queryFn: () => getProductManagementSummary(filters),
    staleTime: SERVER_STATE_STALE_TIME.summary,
    enabled,
  });
}

export function useProductManagementOptionsQuery(filters: ProductManagementFilters) {
  return useQuery({
    queryKey: productManagementKeys.options(filters),
    queryFn: () => getProductManagementOptions(filters),
    staleTime: SERVER_STATE_STALE_TIME.options,
    placeholderData: keepPreviousData,
  });
}

export function useProductManagementDetailQuery(row?: ProductManagementRow) {
  return useQuery({
    queryKey: productManagementKeys.detail(row?.id ?? "none"),
    queryFn: () => {
      if (!row) throw new Error("PRODUCT_DETAIL_ROW_REQUIRED");
      return getProductManagementSku(row);
    },
    enabled: Boolean(row),
    staleTime: SERVER_STATE_STALE_TIME.detail,
    placeholderData: row,
  });
}

export function useProductManagementTableViewQuery() {
  return useQuery({
    queryKey: productManagementKeys.tableView,
    queryFn: getProductManagementTableView,
    staleTime: SERVER_STATE_STALE_TIME.preferences,
  });
}

export function useSaveProductManagementTableViewMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      appliedColumnKeys,
      columnWidths,
    }: {
      appliedColumnKeys: string[];
      columnWidths: Record<string, number>;
    }) => saveProductManagementTableView(appliedColumnKeys, columnWidths),
    onSuccess: (view) => {
      queryClient.setQueryData(productManagementKeys.tableView, view);
    },
  });
}

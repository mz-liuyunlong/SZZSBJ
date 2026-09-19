import { backendRequest } from "@/api/backendApi";
import {
  EMPTY_REPORT_FILTER_OPTIONS,
  normalizeReportFilterOptions,
  type ReportFilterOption,
} from "@/shared/report-filters";

export type SalesFilterOption = ReportFilterOption;

export interface SalesFilterOptions {
  platforms: SalesFilterOption[];
  owners: SalesFilterOption[];
  stores: SalesFilterOption[];
}

export interface SalesFilterOptionsParams {
  startDate?: string;
  endDate?: string;
  platforms?: string[];
  owners?: string[];
  stores?: string[];
  searchField?: string;
  keyword?: string;
  signal?: AbortSignal;
}

export const emptySalesFilterOptions: SalesFilterOptions = {
  platforms: EMPTY_REPORT_FILTER_OPTIONS,
  owners: EMPTY_REPORT_FILTER_OPTIONS,
  stores: EMPTY_REPORT_FILTER_OPTIONS,
};

const backendSearchField = (field: string | undefined) => {
  if (field === "productId") return "item_id";
  if (field === "productName") return "product_name";
  return field ?? "sku";
};

const appendMultiParam = (
  search: URLSearchParams,
  key: string,
  values: string[] | undefined,
) => {
  const normalized = (values ?? []).map((value) => value.trim()).filter(Boolean);
  if (normalized.length > 0) search.set(key, normalized.join(","));
};

export { mergeSelectedFilterOptions, mergeSelectedFilterValues } from "@/shared/report-filters";

export async function fetchSalesFilterOptions(
  params: SalesFilterOptionsParams,
): Promise<SalesFilterOptions> {
  const search = new URLSearchParams();

  if (params.startDate) search.set("start_date", params.startDate);
  if (params.endDate) search.set("end_date", params.endDate);
  appendMultiParam(search, "platform", params.platforms);
  appendMultiParam(search, "owner_ref", params.owners);
  appendMultiParam(search, "store_id", params.stores);

  const keyword = params.keyword?.trim();
  if (keyword) {
    search.set("search_field", backendSearchField(params.searchField));
    search.set("keyword", keyword);
  }

  const suffix = search.toString();

  const envelope = await backendRequest<SalesFilterOptions, unknown>(
    `/api/data-pages/filter-options${suffix ? `?${suffix}` : ""}`,
    params.signal ? { signal: params.signal } : undefined,
  );

  return {
    platforms: normalizeReportFilterOptions(envelope.data.platforms),
    owners: normalizeReportFilterOptions(envelope.data.owners),
    stores: normalizeReportFilterOptions(envelope.data.stores),
  };
}

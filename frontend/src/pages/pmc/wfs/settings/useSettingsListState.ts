/** Committed search / filters / sort / page state for the PMC 设置 list pages (sent to the server as query params). */
import { useState } from "react";
import { REPORT_TABLE_DEFAULT_PAGE_SIZE } from "@/components/report-table/pagination";
import type { SettingsSearch } from "./SettingsListLayout";

export type SortOrder = "asc" | "desc";

export function useSettingsListState<F extends Record<string, string | undefined>, S extends string>(defaultSort: S) {
  const [search, setSearchState] = useState<SettingsSearch>({ keyword: "", field: "all" });
  const [filters, setFilters] = useState<Partial<F>>({});
  const [sort, setSortState] = useState<{ by: S; order: SortOrder }>({ by: defaultSort, order: "asc" });
  const [pagination, setPagination] = useState({ page: 1, pageSize: REPORT_TABLE_DEFAULT_PAGE_SIZE });
  const firstPage = () => setPagination((p) => ({ ...p, page: 1 }));
  return {
    search,
    filters,
    sort,
    pagination,
    setSearch: (next: SettingsSearch) => { setSearchState(next); firstPage(); },
    setFilter: <K extends keyof F>(key: K, value: F[K] | undefined) => { setFilters((f) => ({ ...f, [key]: value })); firstPage(); },
    setSort: (by: S, order: SortOrder) => { setSortState({ by, order }); firstPage(); },
    setPagination: (page: number, pageSize: number) => setPagination({ page, pageSize }),
    reset: () => {
      setSearchState({ keyword: "", field: "all" });
      setFilters({});
      setSortState({ by: defaultSort, order: "asc" });
      setPagination((p) => ({ ...p, page: 1 }));
    },
    /** Base query params shared by every list endpoint (SEARCH_FILTER_SORT_RULES 推荐参数). */
    query: {
      page: pagination.page,
      page_size: pagination.pageSize,
      keyword: search.keyword || undefined,
      search_field: search.field,
      sort_by: sort.by,
      sort_order: sort.order,
    },
  };
}

/** ProTable sorter → whitelisted sort key; columns without a sort key fall back to the default. */
export function sortFromTable<S extends string>(
  sorter: unknown,
  allowed: readonly S[],
  fallback: S,
): { by: S; order: SortOrder } {
  const one = (Array.isArray(sorter) ? sorter[0] : sorter) as { columnKey?: string; order?: "ascend" | "descend" | null } | undefined;
  const key = one?.columnKey as S | undefined;
  if (!one?.order || !key || !allowed.includes(key)) return { by: fallback, order: "asc" };
  return { by: key, order: one.order === "descend" ? "desc" : "asc" };
}

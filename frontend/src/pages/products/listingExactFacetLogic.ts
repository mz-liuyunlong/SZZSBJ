import { useEffect, useRef, useState } from "react";
import type { ReportFilterOption } from "@/shared/report-filters";
import { fetchListingExactFacetBatchOptions, type ListingManagementParams } from "@/pages/products/listingManagementApi";

export const listingMainFacets = [
  ["store", "全部店铺"], ["owner", "负责人"], ["archiveStatus", "归档状态"],
  ["productTags", "产品标签"], ["tags", "自定义标签"], ["lifecycle", "生命周期"],
  ["productGrade", "Listing等级"],
] as const;

export const listingMoreFacetGroups = [
  { title: "商品内容", fields: [["imageCount", "图片数量"], ["keyFeatures", "五点描述"]] },
  { title: "价格", fields: [["hasStrikethrough", "有无划线价"], ["salePrice", "在售价"]] },
  { title: "库存与上架", fields: [["wfsAvailableInventory", "WFS可售库存"], ["inboundInventory", "在途库存"], ["listedAt", "上架时间"]] },
  { title: "状态与评价", fields: [["listingStatus", "Listing状态"], ["buyBoxStatus", "购物车状态"], ["rating", "评分"], ["reviewCount", "评论数"]] },
  { title: "卖家与跟卖", fields: [["brand", "品牌"], ["walmartSeller", "Walmart卖家"], ["sellerOfferCount", "卖家数量"], ["resold", "是否被跟卖"], ["checkedAt", "监控日期"]] },
  { title: "履约与识别", fields: [["fulfillmentMethod", "发货方式"]] },
  { title: "分析与归档", fields: [["archiveReason", "归档原因"]] },
] as const;

const visibleFacetFields = new Set<string>([
  ...listingMainFacets.map(([field]) => field),
  ...listingMoreFacetGroups.flatMap<string>(
    group => group.fields.map(([field]) => field),
  ),
]);

export function visibleListingExactFilters(
  filters?: Record<string, string[]>,
): Record<string, string[]> {
  return Object.fromEntries(
    Object.entries(filters ?? {}).filter(
      ([field]) => visibleFacetFields.has(field),
    ),
  );
}

export type MoreFacetState = { options: ReportFilterOption[]; ready: boolean; loading: boolean };
export const listingMoreFields = listingMoreFacetGroups.flatMap<string>(
  group => group.fields.map(([field]) => field),
);

export function listingMoreDraft(exact: Record<string, string[]>): Record<string, string[]> {
  return Object.fromEntries(Object.entries(exact).filter(([field, values]) =>
    listingMoreFields.includes(field) && values.length,
  ));
}

export function mergeListingMoreDraft(
  exact: Record<string, string[]>, draft: Record<string, string[]>,
): Record<string, string[]> {
  const result = Object.fromEntries(Object.entries(exact).filter(([field]) =>
    !listingMoreFields.includes(field),
  ));
  return { ...result, ...listingMoreDraft(draft) };
}

export function listingMoreFacetScope(query: ListingManagementParams, field: string): string {
  const exactFilters = Object.fromEntries(Object.entries(query.exactFilters ?? {})
    .filter(([key, values]) => key !== field && values.length)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, values]) => [key, [...new Set(values)].sort()]));
  return JSON.stringify({ ...query, exactFilters });
}

export function useListingMoreFacetOptions(
  query: ListingManagementParams, revision: number,
  onError: (message: string) => void,
  enabled = true,
): Record<string, MoreFacetState> {
  const cache = useRef<Record<string, { key: string; options: ReportFilterOption[] }>>({});
  const previous = useRef<Record<string, { key: string; options: ReportFilterOption[] }>>({});
  const cacheRevision = useRef(revision);
  const [results, setResults] = useState<Record<string, MoreFacetState>>({});
  const errorRef = useRef(onError);
  useEffect(() => { errorRef.current = onError; }, [onError]);
  const scope = listingMoreFacetScope(query, "");
  useEffect(() => {
    // Automatic prefetch after the primary table's first paint. Opening early
    // explicitly bypasses the gate; an unchanged open/close does not refetch.
    if (!enabled) return;
    const params = JSON.parse(scope) as ListingManagementParams;
    const keys = Object.fromEntries(listingMoreFields.map(field =>
      [field, `${revision}:${listingMoreFacetScope(params, field)}`],
    ));
    if (cacheRevision.current !== revision) {
      previous.current = {};
      cacheRevision.current = revision;
    }
    for (const field of listingMoreFields) {
      const stored = previous.current[field];
      if (cache.current[field]?.key !== keys[field] && stored?.key === keys[field]) {
        const latest = cache.current[field];
        cache.current[field] = stored;
        if (latest) previous.current[field] = latest;
        else delete previous.current[field];
      }
    }
    const changed = listingMoreFields.filter(field => cache.current[field]?.key !== keys[field]);
    const changedSet = new Set(changed);
    const initial = Object.keys(cache.current).length === 0;
    let active = true;
    const controller = new AbortController();
    const snapshot = (pending: boolean) => Object.fromEntries(listingMoreFields.map(field => [field, {
      options: cache.current[field]?.options ?? [],
      ready: cache.current[field] !== undefined,
      loading: pending && changedSet.has(field),
    }]));
    setResults(snapshot(true));
    if (!changed.length) return;
    const run = async () => {
      const timeout = window.setTimeout(() => controller.abort(), 30_000);
      try {
        const fields = Object.fromEntries(changed.map(field => [field, 0]));
        // Exactly one HTTP request, no browser-side paging loop.
        const pages = await fetchListingExactFacetBatchOptions(fields, params, controller.signal);
        if (!active) return;
        for (const field of changed) {
          const page = pages[field];
          if (!page || !Array.isArray(page.options) || page.has_more) {
            throw new Error("incomplete facet batch");
          }
        }
        for (const field of changed) {
          const latest = cache.current[field];
          if (latest && latest.key.startsWith(`${revision}:`)) previous.current[field] = latest;
          cache.current[field] = { key: keys[field], options: pages[field].options };
        }
        setResults(snapshot(false));
      } catch {
        if (!active) return;
        setResults(snapshot(false));
        errorRef.current("更多筛选加载失败或超时，请缩小顶部筛选范围后重试");
      } finally {
        window.clearTimeout(timeout);
      }
    };
    const timer = window.setTimeout(() => { void run(); }, initial ? 0 : 180);
    return () => {
      active = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [enabled, revision, scope]);
  return results;
}

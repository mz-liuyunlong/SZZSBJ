/** Listing table ordering contract. Preserve the user's order of selection. */
export const listingSortFields = [
  "productIdName", "skuMsku", "imageCount", "listPrice", "hasStrikethrough",
  "salePrice", "wfsAvailableInventory", "inboundInventory", "listedAt",
  "sales90Days", "adSpend30Days", "lifecycle", "productGrade", "listingStatus",
  "buyBoxStatus", "sellerOfferCount", "resold", "checkedAt", "rating", "reviewCount",
] as const;

export type ListingSortField = typeof listingSortFields[number];
export type ListingSort = { key: ListingSortField; direction: "asc" | "desc" };
const allowed: ReadonlySet<string> = new Set(listingSortFields);
export const isListingSortField = (key: unknown): key is ListingSortField =>
  typeof key === "string" && allowed.has(key);

export type ListingSortEvent = { columnKey?: unknown; order?: unknown };

export function nextListingColumnSort(
  previous: readonly ListingSort[], key: ListingSortField,
): ListingSort[] {
  const current = previous.find(sort => sort.key === key);
  if (!current) return [{ key, direction: "asc" }];
  if (current.direction === "asc") return [{ key, direction: "desc" }];
  return [];
}

export function mergeListingSorts(
  previous: readonly ListingSort[], event: ListingSortEvent | ListingSortEvent[],
): ListingSort[] {
  const active: ListingSort[] = [];

  for (const item of Array.isArray(event) ? event : [event]) {
    if (!isListingSortField(item.columnKey)) continue;
    if (item.order !== "ascend" && item.order !== "descend") continue;

    active.push({
      key: item.columnKey,
      direction: item.order === "ascend" ? "asc" : "desc",
    });
  }

  const next = active.find(sort => sort.key !== previous[0]?.key) ?? active[0];
  return next ? [next] : [];
}

export const encodeListingSorts = (sorts?: readonly ListingSort[]) =>
  (sorts ?? []).map(({ key, direction }) => `${key}:${direction}`).join(",");

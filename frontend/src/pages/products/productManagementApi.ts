import { backendRequest } from "@/api/backendApi";
import type {
  ProductGrade,
  ProductManagementFilters,
  ProductManagementRow,
  ProductTag,
} from "@/pages/products/productManagementTypes";

interface BackendTag { key: string; label: string; color: string | null }
interface BackendListItem {
  sku_id: string;
  sku: string | null;
  product_name: string | null;
  primary_image: string | null;
  internal_tags: BackendTag[];
  category: string | null;
  purchase_cost_cny: string | null;
  unit_first_leg_cost: string | null;
  unit_first_leg_currency_code: string | null;
  purchase_delivery_days: number | null;
  data_quality_score: string | null;
  linked_platform_sku_count: number;
  source_observed_at: string | null;
  product_grade: "A" | "B" | "C" | "exception" | null;
  wfs_fulfillment_fee: string | null;
  wfs_fulfillment_fee_currency_code: string | null;
  wfs_daily_storage_fee: string | null;
  suggested_price_usd: string | null;
  minimum_price_usd: string | null;
  clearance_price_usd: string | null;
}

interface BackendDetail {
  sku_id: string;
  core: {
    category: string | null;
  } | null;
  synced_detail: {
    purchase_delivery_days: number | null;
    purchase_material: string | null;
    customs_export_name_cn: string | null;
    customs_import_name_en: string | null;
    clearance_material_cn: string | null;
    clearance_usage_cn: string | null;
    clearance_material_en: string | null;
    product_length_cm: string | null;
    product_width_cm: string | null;
    product_height_cm: string | null;
    product_net_weight_g: string | null;
    product_gross_weight_g: string | null;
    package_length_cm: string | null;
    package_width_cm: string | null;
    package_height_cm: string | null;
    box_length_cm: string | null;
    box_width_cm: string | null;
    box_height_cm: string | null;
    source_observed_at: string;
  } | null;
  images: Array<{ ordinal: number; url: string; is_primary: boolean | null }>;
  internal_tags: BackendTag[];
  source_tags: Array<{ source_tag_id: string | null; label: string | null; color: string | null }>;
}

interface ListMeta { total: number | null }
interface BackendOptions { product_grades: string[]; internal_tags: BackendTag[] }
interface BackendTableView {
  applied_column_keys: string[];
  column_widths: Record<string, number>;
}

const gradeLabels: Record<string, ProductManagementRow["productGrade"]> = {
  A: "A级",
  B: "B级",
  C: "C级",
  exception: "异常",
};

const gradeValues: Record<ProductGrade | "异常", string> = {
  A级: "A",
  B级: "B",
  C级: "C",
  异常: "exception",
};

const money = (currency: string | null, value: string | null) => (
  value === null ? null : `${currency ?? ""} ${value}`.trim()
);

const dimensions = (...values: Array<string | null>) => (
  values.every((value) => value !== null) ? values.join(" × ") : null
);

export const toProductManagementRow = (item: BackendListItem): ProductManagementRow => ({
  id: item.sku_id,
  image: item.primary_image,
  images: item.primary_image ? [item.primary_image] : [],
  sku: item.sku,
  productName: item.product_name,
  tags: item.internal_tags.map((tag) => tag.label),
  productGrade: item.product_grade ? gradeLabels[item.product_grade] : null,
  category: item.category,
  purchasePrice: money("CNY", item.purchase_cost_cny),
  firstLegFreight: money(item.unit_first_leg_currency_code, item.unit_first_leg_cost),
  wfsDeliveryFee: money(
    item.wfs_fulfillment_fee_currency_code,
    item.wfs_fulfillment_fee,
  ),
  purchaseLeadTime: item.purchase_delivery_days === null
    ? null
    : `${item.purchase_delivery_days}天`,
  storageFee: money("USD", item.wfs_daily_storage_fee),
  wfsFee: money(item.wfs_fulfillment_fee_currency_code, item.wfs_fulfillment_fee),
  suggestedPrice: money("USD", item.suggested_price_usd),
  minimumPrice: money("USD", item.minimum_price_usd),
  clearancePrice: money("USD", item.clearance_price_usd),
  materialCn: null,
  materialEn: null,
  usageCn: null,
  usageEn: null,
  customsNameCn: null,
  customsNameEn: null,
  packageSpec: null,
  cartonSpec: null,
  productSpec: null,
  grossWeightKg: null,
  netWeightKg: null,
  dataCompleteness: item.data_quality_score === null
    ? null
    : Number(item.data_quality_score),
  linkedPlatformSkuCount: item.linked_platform_sku_count,
  updatedAt: item.source_observed_at,
});

function listQuery(
  filters: ProductManagementFilters,
  page: number,
  pageSize: number,
) {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  const keyword = filters.keyword.trim();
  if (keyword) {
    query.set(
      filters.searchType === "productName"
        ? "product_name"
        : filters.searchType === "category"
          ? "category"
          : "sku",
      keyword,
    );
  }
  for (const sku of filters.batchValues ?? []) query.append("sku_batch", sku);
  if (filters.productGrade) query.set("product_grade", gradeValues[filters.productGrade]);
  if (filters.tag) query.set("internal_tag", filters.tag);
  return query;
}

export async function listProductManagementSkus(
  filters: ProductManagementFilters,
  page: number,
  pageSize: number,
) {
  const response = await backendRequest<{ items: BackendListItem[] }, ListMeta>(
    `/api/product-management/skus?${listQuery(filters, page, pageSize)}`,
  );
  return {
    rows: response.data.items.map(toProductManagementRow),
    total: response.meta.total ?? 0,
  };
}

export async function getProductManagementSku(
  row: ProductManagementRow,
): Promise<ProductManagementRow> {
  const response = await backendRequest<BackendDetail>(
    `/api/product-management/skus/${encodeURIComponent(row.id)}`,
  );
  const detail = response.data.synced_detail;
  return {
    ...row,
    image: response.data.images.find((image) => image.is_primary)?.url
      ?? response.data.images[0]?.url
      ?? row.image,
    images: response.data.images.map((image) => image.url),
    category: response.data.core?.category ?? row.category,
    tags: [
      ...response.data.internal_tags.map((tag) => tag.label),
      ...response.data.source_tags.flatMap((tag) => tag.label ? [tag.label] : []),
    ],
    purchaseLeadTime: detail?.purchase_delivery_days === null || !detail
      ? null
      : `${detail.purchase_delivery_days}天`,
    materialCn: detail?.purchase_material ?? null,
    materialEn: detail?.clearance_material_en ?? null,
    usageCn: detail?.clearance_usage_cn ?? null,
    usageEn: null,
    customsNameCn: detail?.customs_export_name_cn ?? null,
    customsNameEn: detail?.customs_import_name_en ?? null,
    packageSpec: detail ? dimensions(
      detail.package_length_cm,
      detail.package_width_cm,
      detail.package_height_cm,
    ) : null,
    cartonSpec: detail ? dimensions(
      detail.box_length_cm,
      detail.box_width_cm,
      detail.box_height_cm,
    ) : null,
    productSpec: detail ? dimensions(
      detail.product_length_cm,
      detail.product_width_cm,
      detail.product_height_cm,
    ) : null,
    grossWeightKg: detail?.product_gross_weight_g
      ? `${detail.product_gross_weight_g} g`
      : null,
    netWeightKg: detail?.product_net_weight_g ? `${detail.product_net_weight_g} g` : null,
    updatedAt: detail?.source_observed_at ?? row.updatedAt,
  } satisfies ProductManagementRow;
}

export async function getProductManagementOptions() {
  const response = await backendRequest<BackendOptions>("/api/product-management/options");
  return {
    grades: response.data.product_grades.flatMap((grade) => {
      const label = gradeLabels[grade];
      return label && label !== "异常" ? [label] : [];
    }) as ProductGrade[],
    tags: response.data.internal_tags.map((tag) => tag.label) as ProductTag[],
  };
}

export async function requestProductManagementExport(
  filters: ProductManagementFilters,
) {
  const query = listQuery(filters, 1, 100);
  return backendRequest<{ status: string; file_created: false }>(
    "/api/product-management/skus/export",
    {
      method: "POST",
      body: JSON.stringify({
        query: {
          sku: query.get("sku"),
          product_name: query.get("product_name"),
          category: query.get("category"),
          sku_batch: query.getAll("sku_batch"),
          product_grade: query.get("product_grade"),
          internal_tag: query.get("internal_tag"),
        },
        max_rows: 5_000,
      }),
    },
  );
}

export async function getProductManagementTableView() {
  return (await backendRequest<BackendTableView>(
    "/api/user-table-views/product-management",
  )).data;
}

export async function saveProductManagementTableView(
  appliedColumnKeys: string[],
  columnWidths: Record<string, number>,
) {
  return (await backendRequest<BackendTableView>(
    "/api/user-table-views/product-management",
    {
      method: "PUT",
      body: JSON.stringify({
        applied_column_keys: appliedColumnKeys,
        column_widths: columnWidths,
      }),
    },
  )).data;
}

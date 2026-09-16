import { backendRequest } from "@/api/backendApi";
import { formatDate } from "@/shared/formatters";
import type {
  ProductGrade,
  ProductManagementFilters,
  ProductManagementRow,
  ProductManagementSummary,
} from "@/pages/products/productManagementTypes";

interface BackendTag { key: string; label: string; color: string | null }
interface BackendListItem {
  sku_id: string;
  sku: string | null;
  product_name: string | null;
  owner_uid: string | null;
  owner_name: string | null;
  product_developer_uid: string | null;
  product_developer_name: string | null;
  primary_image: string | null;
  primary_image_thumbnail_url: string | null;
  primary_image_preview_url: string | null;
  image_count: number;
  internal_tags: BackendTag[];
  source_tags: Array<{
    source_tag_id: string | null;
    label: string | null;
    color: string | null;
  }>;
  category: string | null;
  purchase_cost_cny: string | null;
  first_leg_fee_cny: string | null;
  purchase_delivery_days: number | null;
  data_quality_score: string | null;
  linked_platform_sku_count: number;
  source_observed_at: string | null;
  product_grade: "A" | "B" | "C" | "exception" | null;
  wfs_fulfillment_fee: string | null;
  wfs_fulfillment_fee_currency_code: string | null;
  wfs_daily_storage_fee: string | null;
  storage_fee_usd: string | null;
  fixed_cost_usd: string | null;
  suggested_price_usd: string | null;
  minimum_price_usd: string | null;
  clearance_price_usd: string | null;
  calculation_status: "ok" | "pricing_unavailable" | "storage_unavailable" | "invalid_denominator";
  root_missing_codes: string[];
  pricing_available: boolean;
  billing_root_complete: boolean;
  wfs_calc_status: string | null;
  wfs_calc_reason: string | null;
  storage_calc_status: string | null;
  first_leg_calc_status: string | null;
  formula_version: string | null;
}

interface BackendDetail {
  sku_id: string;
  core: {
    category: string | null;
  } | null;
  synced_detail: {
    owner_uid: string | null;
    owner_name: string | null;
    product_developer_uid: string | null;
    product_developer_name: string | null;
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
  images: Array<{
    ordinal: number;
    url: string;
    thumbnail_url: string | null;
    preview_url: string | null;
    is_primary: boolean | null;
  }>;
  internal_tags: BackendTag[];
  source_tags: Array<{ source_tag_id: string | null; label: string | null; color: string | null }>;
  pricing: {
    calculation_status: "ok" | "pricing_unavailable" | "storage_unavailable" | "invalid_denominator";
    root_missing_codes: string[];
    pricing_available: boolean;
    billing_root_complete: boolean;
    purchase_cost_cny: string | null;
    product_gross_weight_g: string | null;
    gross_weight_kg: string | null;
    package_length_cm: string | null;
    package_width_cm: string | null;
    package_height_cm: string | null;
    first_leg_volume_weight_kg: string | null;
    first_leg_chargeable_weight_kg: string | null;
    first_leg_cost_per_kg_cny: string | null;
    first_leg_fee_cny: string | null;
    wfs_actual_weight_lb: string | null;
    wfs_dimensional_weight_lb: string | null;
    wfs_chargeable_weight_lb: string | null;
    wfs_weight_padding_lb: string | null;
    wfs_base_fee_usd: string | null;
    wfs_fulfillment_fee_usd: string | null;
    package_volume_cuft: string | null;
    daily_storage_fee_per_unit_usd: string | null;
    storage_fee_usd: string | null;
    fixed_cost_usd: string | null;
    usd_cny_rate: string | null;
    commission_rate: string | null;
    after_sales_rate: string | null;
    ad_cost_rate: string | null;
    suggested_margin_rate: string | null;
    minimum_margin_rate: string | null;
    suggested_price_usd: string | null;
    minimum_price_usd: string | null;
    clearance_price_usd: string | null;
    wfs_calc_status: string;
    wfs_calc_reason: string | null;
    storage_calc_status: string;
    first_leg_calc_status: string;
    detail_messages: string[];
    formula_version: string | null;
    wfs_formula_version: string | null;
  } | null;
}

interface ListMeta { total: number | null }
interface BackendSummary {
  total: number;
  synced_detail_count: number;
  data_completeness_rate: string;
  with_image_count: number;
  with_source_tag_count: number;
  incomplete_count: number;
  missing_purchase_cost_count: number;
  missing_purchase_delivery_count: number;
  missing_gross_weight_count: number;
  missing_package_dimensions_count: number;
  missing_image_count: number;
  missing_dimension_image_count: number;
  invalid_pricing_rule_count: number;
  pricing_ok_count: number;
}
interface BackendPersonOption { uid: string; name: string; count?: number }
interface BackendSourceTagOption { value: string; label: string; color: string | null; count?: number }
interface BackendGradeOption { value: string; label: string; count?: number }
interface BackendOptions {
  product_grades: string[];
  product_grade_options?: BackendGradeOption[];
  internal_tags: BackendTag[];
  owners: BackendPersonOption[];
  developers: BackendPersonOption[];
  source_tags: BackendSourceTagOption[];
}
interface BackendTableView {
  applied_column_keys: string[];
  column_widths: Record<string, number>;
  schema_version: number;
  view_key: string;
  updated_at: string | null;
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



const currencySymbolMap: Record<string, string> = {
  CNY: "¥",
  USD: "$",
};

const money = (currency: string | null, value: string | null | undefined) => {
  if (value == null) return null;

  const normalizedValue = String(value)
    .replace(/^CNY\s*/i, "")
    .replace(/^USD\s*/i, "");

  const symbol = currency ? (currencySymbolMap[currency] ?? currency) : "";

  return `${symbol}${normalizedValue}`.trim();
};

const dateOnly = (value: string | null) => (
  value ? formatDate(value) : null
);

const dimensions = (...values: Array<string | null>) => (
  values.every((value) => value !== null) ? values.join(" × ") : null
);


const getDailyStorageFeePerUnitUsd = (item: BackendListItem) => {
  const record = item as BackendListItem & {
    data?: {
      pricing?: {
        daily_storage_fee_per_unit_usd?: string | null;
      };
    };
    pricing?: {
      daily_storage_fee_per_unit_usd?: string | null;
    };
  };

  return (
    record.data?.pricing?.daily_storage_fee_per_unit_usd ??
    record.pricing?.daily_storage_fee_per_unit_usd ??
    item.wfs_daily_storage_fee ??
    null
  );
};

export const toProductManagementRow = (item: BackendListItem): ProductManagementRow => ({
  id: item.sku_id,
  image: item.primary_image_thumbnail_url ?? item.primary_image,
  previewImage: (
    item.primary_image_preview_url
    ?? item.primary_image_thumbnail_url
    ?? item.primary_image
  ),
  sourceImage: item.primary_image,
  images: item.primary_image_preview_url
    ? [item.primary_image_preview_url]
    : item.primary_image_thumbnail_url
      ? [item.primary_image_thumbnail_url]
      : item.primary_image
        ? [item.primary_image]
        : [],
  imageCount: item.image_count,
  sku: item.sku,
  productName: item.product_name,
  tags: item.internal_tags.map((tag) => tag.label),
  sourceTags: item.source_tags.flatMap((tag) => tag.label ? [tag.label] : []),
  sourceTagColors: Object.fromEntries(
    item.source_tags.flatMap((tag) => (
      tag.label ? [[tag.label, tag.color]] : []
    )),
  ),
  ownerUid: item.owner_uid,
  ownerName: item.owner_name,
  developerUid: item.product_developer_uid,
  developerName: item.product_developer_name,
  productGrade: item.product_grade ? gradeLabels[item.product_grade] : null,
  category: item.category,
  purchasePrice: money("CNY", item.purchase_cost_cny),
  firstLegFreight: money("CNY", item.first_leg_fee_cny),
  wfsDeliveryFee: money(
    item.wfs_fulfillment_fee_currency_code,
    item.wfs_fulfillment_fee,
  ),
  purchaseLeadTime: item.purchase_delivery_days === null
    ? null
    : `${item.purchase_delivery_days}天`,
  storageFee: money("USD", getDailyStorageFeePerUnitUsd(item)),
  wfsFee: money(item.wfs_fulfillment_fee_currency_code, item.wfs_fulfillment_fee),
  suggestedPrice: money("USD", item.suggested_price_usd),
  minimumPrice: money("USD", item.minimum_price_usd),
  clearancePrice: money("USD", item.clearance_price_usd),
  calculationStatus: item.calculation_status,
  rootMissingCodes: item.root_missing_codes,
  pricingAvailable: item.pricing_available,
  billingRootComplete: item.billing_root_complete,
  wfsCalculationStatus: item.wfs_calc_status,
  wfsCalculationReason: item.wfs_calc_reason,
  storageCalculationStatus: item.storage_calc_status,
  firstLegCalculationStatus: item.first_leg_calc_status,
  formulaVersion: item.formula_version,
  pricingBreakdown: null,
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
  updatedAt: dateOnly(item.source_observed_at),
});

function listQuery(
  filters: ProductManagementFilters,
  page: number,
  pageSize: number,
  includeIssue = true,
) {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  const batchValues = filters.batchValues ?? [];
  if (batchValues.length > 0) {
    for (const sku of batchValues) query.append("sku_batch", sku);
  } else {
    const keyword = filters.keyword.trim();
    if (keyword) query.set("sku", keyword);
  }
  if (filters.ownerUid) query.set("owner_uid", filters.ownerUid);
  if (filters.developerUid) query.set("developer_uid", filters.developerUid);
  if (filters.tag) query.set("source_tag", filters.tag);
  if (filters.productGrade) query.set("product_grade", gradeValues[filters.productGrade]);
  if (includeIssue && filters.issueCode) query.set("issue_code", filters.issueCode);
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

export async function getProductManagementSummary(
  filters: ProductManagementFilters,
): Promise<ProductManagementSummary> {
  const query = listQuery(filters, 1, 1, false);
  query.delete("page");
  query.delete("page_size");
  const response = await backendRequest<BackendSummary>(
    `/api/product-management/skus/summary?${query}`,
  );
  return {
    total: response.data.total,
    syncedDetailCount: response.data.synced_detail_count,
    dataCompletenessRate: Number(response.data.data_completeness_rate),
    withImageCount: response.data.with_image_count,
    withSourceTagCount: response.data.with_source_tag_count,
    incompleteCount: response.data.incomplete_count,
    missingPurchaseCostCount: response.data.missing_purchase_cost_count,
    missingPurchaseDeliveryCount: response.data.missing_purchase_delivery_count,
    missingGrossWeightCount: response.data.missing_gross_weight_count,
    missingPackageDimensionsCount: response.data.missing_package_dimensions_count,
    missingImageCount: response.data.missing_image_count,
    missingDimensionImageCount: response.data.missing_dimension_image_count,
    invalidPricingRuleCount: response.data.invalid_pricing_rule_count,
    pricingOkCount: response.data.pricing_ok_count,
  };
}

export async function getProductManagementSku(
  row: ProductManagementRow,
): Promise<ProductManagementRow> {
  const response = await backendRequest<BackendDetail>(
    `/api/product-management/skus/${encodeURIComponent(row.id)}`,
  );
  const detail = response.data.synced_detail;
  const pricing = response.data.pricing;
  const primaryImage = (
    response.data.images.find((image) => image.is_primary)
    ?? response.data.images[0]
  );
  return {
    ...row,
    image: (
      primaryImage?.thumbnail_url
      ?? primaryImage?.url
      ?? row.image
    ),
    previewImage: (
      primaryImage?.preview_url
      ?? primaryImage?.thumbnail_url
      ?? primaryImage?.url
      ?? row.previewImage
      ?? row.image
    ),
    sourceImage: primaryImage?.url ?? row.sourceImage ?? row.image,
    images: response.data.images.map((image) => (
      image.preview_url ?? image.thumbnail_url ?? image.url
    )),
    imageCount: response.data.images.length,
    category: response.data.core?.category ?? row.category,
    tags: response.data.internal_tags.map((tag) => tag.label),
    sourceTags: response.data.source_tags.flatMap((tag) => tag.label ? [tag.label] : []),
    sourceTagColors: Object.fromEntries(
      response.data.source_tags.flatMap((tag) => (
        tag.label ? [[tag.label, tag.color]] : []
      )),
    ),
    ownerUid: detail?.owner_uid ?? row.ownerUid,
    ownerName: detail?.owner_name ?? row.ownerName,
    developerUid: detail?.product_developer_uid ?? row.developerUid,
    developerName: detail?.product_developer_name ?? row.developerName,
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
    purchasePrice: money("CNY", pricing?.purchase_cost_cny ?? null),
    firstLegFreight: money("CNY", pricing?.first_leg_fee_cny ?? null),
    wfsDeliveryFee: money("USD", pricing?.wfs_fulfillment_fee_usd ?? null),
    wfsFee: money("USD", pricing?.wfs_fulfillment_fee_usd ?? null),
    storageFee: money("USD", pricing?.storage_fee_usd ?? null),
    suggestedPrice: money("USD", pricing?.suggested_price_usd ?? null),
    minimumPrice: money("USD", pricing?.minimum_price_usd ?? null),
    clearancePrice: money("USD", pricing?.clearance_price_usd ?? null),
    calculationStatus: pricing?.calculation_status ?? row.calculationStatus,
    rootMissingCodes: pricing?.root_missing_codes ?? row.rootMissingCodes,
    pricingAvailable: pricing?.pricing_available ?? row.pricingAvailable,
    billingRootComplete: pricing?.billing_root_complete ?? row.billingRootComplete,
    wfsCalculationStatus: pricing?.wfs_calc_status ?? row.wfsCalculationStatus,
    wfsCalculationReason: pricing?.wfs_calc_reason ?? row.wfsCalculationReason,
    storageCalculationStatus: pricing?.storage_calc_status ?? row.storageCalculationStatus,
    firstLegCalculationStatus: pricing?.first_leg_calc_status ?? row.firstLegCalculationStatus,
    formulaVersion: pricing?.formula_version ?? row.formulaVersion,
    pricingBreakdown: pricing ? {
      productGrossWeightG: pricing.product_gross_weight_g,
      grossWeightKg: pricing.gross_weight_kg,
      packageLengthCm: pricing.package_length_cm,
      packageWidthCm: pricing.package_width_cm,
      packageHeightCm: pricing.package_height_cm,
      firstLegVolumeWeightKg: pricing.first_leg_volume_weight_kg,
      firstLegChargeableWeightKg: pricing.first_leg_chargeable_weight_kg,
      firstLegCostPerKgCny: pricing.first_leg_cost_per_kg_cny,
      wfsActualWeightLb: pricing.wfs_actual_weight_lb,
      wfsDimensionalWeightLb: pricing.wfs_dimensional_weight_lb,
      wfsChargeableWeightLb: pricing.wfs_chargeable_weight_lb,
      wfsWeightPaddingLb: pricing.wfs_weight_padding_lb,
      wfsBaseFeeUsd: pricing.wfs_base_fee_usd,
      packageVolumeCuft: pricing.package_volume_cuft,
      dailyStorageFeeUsd: pricing.daily_storage_fee_per_unit_usd,
      fixedCostUsd: pricing.fixed_cost_usd,
      usdCnyRate: pricing.usd_cny_rate,
      commissionRate: pricing.commission_rate,
      afterSalesRate: pricing.after_sales_rate,
      adCostRate: pricing.ad_cost_rate,
      suggestedMarginRate: pricing.suggested_margin_rate,
      minimumMarginRate: pricing.minimum_margin_rate,
      detailMessages: pricing.detail_messages,
      formulaVersion: pricing.formula_version,
      wfsFormulaVersion: pricing.wfs_formula_version,
    } : null,
    updatedAt: detail?.source_observed_at ?? row.updatedAt,
  } satisfies ProductManagementRow;
}

export async function getProductManagementOptions(filters?: ProductManagementFilters) {
  const query = filters ? listQuery(filters, 1, 1, false) : new URLSearchParams();
  query.delete("page");
  query.delete("page_size");
  const suffix = query.toString();
  const response = await backendRequest<BackendOptions>(
    `/api/product-management/options${suffix ? `?${suffix}` : ""}`,
  );
  const gradeOptions = response.data.product_grade_options?.flatMap((option) => {
    const label = gradeLabels[option.value];
    return label && label !== "异常"
      ? [{ value: label as ProductGrade, label: label as ProductGrade, count: option.count ?? 0 }]
      : [];
  }) ?? response.data.product_grades.flatMap((grade) => {
    const label = gradeLabels[grade];
    return label && label !== "异常"
      ? [{ value: label as ProductGrade, label: label as ProductGrade, count: undefined }]
      : [];
  });

  return {
    grades: gradeOptions.map((option) => option.value),
    gradeOptions,
    owners: response.data.owners,
    developers: response.data.developers,
    tags: response.data.source_tags,
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
          owner_uid: query.get("owner_uid"),
          developer_uid: query.get("developer_uid"),
          source_tag: query.get("source_tag"),
          issue_code: query.get("issue_code"),
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

/** Listing-management page backed by DATA-PAGES MART API. */

import { useCallback, useEffect, useMemo, useRef, useState, type Key } from "react";
import { Card, Form, Input, Modal, message } from "antd";

import PageShell from "@/components/page/PageShell";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import CustomTagManagerModal, { type CustomProductTag } from "@/components/product-tags/CustomTagManagerModal";
import ProductTagAssignmentModal from "@/components/product-tags/ProductTagAssignmentModal";
import RuntimeColumnConfigDrawer, {
  type RuntimeColumnGroup,
} from "@/components/report-table/RuntimeColumnConfigDrawer";
import {
  REPORT_TABLE_DEFAULT_PAGE_SIZE,
  normalizeReportTablePageSize,
} from "@/components/report-table/pagination";
import { useElementScrollRestoration } from "@/shared/page-state/useElementScrollRestoration";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import ListingAnalysisModal, { type ListingAnalysisSource } from "@/shared/listing-analysis";
import type { NavigationPage } from "@/config/navigation";

import ListExportModal, {
  type ListExportColumnGroup,
} from "@/pages/products/components/ListExportModal";
import ListingManagementSummaryCards, {
  type ListingManagementSummaryCardKey,
} from "@/pages/products/components/ListingManagementSummaryCards";
import ListingManagementTable from "@/pages/products/components/ListingManagementTable";
import ListingManagementToolbar, {
  type ListingManagementFilters,
} from "@/pages/products/components/ListingManagementToolbar";
import {
  archiveListingManagementRow,
  batchSetListingTags,
  createListingTag,
  deleteListingTag,
  exportListingManagementRows,
  fetchListingGptAnalysisLink,
  fetchListingManagementFilterOptions,
  fetchListingManagementRows,
  fetchListingManagementSummary,
  fetchListingTags,
  restoreListingManagementRow,
  saveListingGptAnalysisLink,
  updateListingTag,
  type ListingManagementFilterOptions,
  type ListingManagementSummary,
} from "@/pages/products/listingManagementApi";
import {
  fixedListingColumnKeys,
  listingColumnFields,
  type ListingManagementRow,
} from "@/pages/products/listingManagementData";

import "@/pages/products/ListingManagementPage.css";

const TEMPLATE_PENDING = "列模板接口待接入";




const createInitialFilters = (): ListingManagementFilters => ({
  stores: [],
  owners: [],
  productTypes: [],
  productStatuses: [],
  tagValues: [],
  archiveStatuses: [],
  searchType: "sku",
  keyword: "",
});

const listingExportColumnGroups: ListExportColumnGroup[] = [
  {
    title: "基础信息",
    fields: [
      { key: "store", label: "店铺" },
      { key: "item_id", label: "商品ID" },
      { key: "sku", label: "SKU" },
      { key: "msku", label: "MSKU" },
      { key: "local_name", label: "品名" },
      { key: "title", label: "标题" },
      { key: "owner", label: "负责人" },
      { key: "developer", label: "开发人" },
      { key: "product_grade", label: "商品等级" },
      { key: "tags", label: "自定义标签" },
    ],
  },
  {
    title: "价格状态",
    fields: [
      { key: "strike_price", label: "划线价" },
      { key: "sale_price", label: "售价" },
      { key: "listing_status", label: "Listing状态" },
      { key: "lifecycle_status", label: "生命周期" },
      { key: "fulfillment_type", label: "发货方式" },
      { key: "buybox_status", label: "购物车状态" },
      { key: "walmart_seller", label: "Walmart卖家" },
      { key: "is_hijacked", label: "是否跟卖" },
    ],
  },
  {
    title: "库存销量",
    fields: [
      { key: "wfs_available_quantity", label: "WFS可售库存" },
      { key: "available_quantity", label: "可售库存" },
      { key: "inbound_quantity", label: "在途库存" },
      { key: "sales_7d", label: "近7天销量" },
      { key: "sales_14d", label: "近14天销量" },
      { key: "sales_30d", label: "近30天销量" },
      { key: "ad_spend_30d", label: "近30天广告费" },
    ],
  },
  {
    title: "评价标识",
    fields: [
      { key: "average_rating", label: "评分" },
      { key: "review_count", label: "评论数" },
      { key: "category", label: "类目" },
      { key: "brand", label: "品牌" },
      { key: "disabled_reason", label: "停用原因" },
      { key: "gtin", label: "GTIN" },
      { key: "upc", label: "UPC" },
      { key: "listed_at", label: "上架时间" },
      { key: "checked_at", label: "检查时间" },
      { key: "archive_status", label: "归档状态" },
      { key: "archive_reason", label: "归档原因" },
    ],
  },
];

const listingDefaultExportColumnKeys = listingExportColumnGroups.flatMap((group) =>
  group.fields.map((field) => field.key),
);

const emptySummary: ListingManagementSummary = {
  total: 0,
  online: 0,
  buyboxException: 0,
  ratingWarning: 0,
  resoldWarning: 0,
  strikePriceException: 0,
};

const emptyFilterOptions: ListingManagementFilterOptions = {
  stores: [],
  owners: [],
  productTypes: [],
  tags: [],
  archiveStatuses: [],
};

const DEFAULT_LISTING_SUMMARY_FILTER_KEY: ListingManagementSummaryCardKey = "total";



const defaultColumnKeys = listingColumnFields.map((field) => field.key);
const defaultColumnWidths: Record<string, number> = {
  image: 72,
  productIdName: 240,
  skuMsku: 190,
  msku: 130,
  productId: 150,
  store: 120,
  owner: 110,
  sku: 130,
  productName: 190,
  title: 260,
  productType: 130,
  listPrice: 110,
  salePrice: 110,
  productStatus: 120,
  lifecycle: 120,
  fulfillmentMethod: 120,
  gptAnalysis: 96,
  listedAt: 140,
  category: 120,
  wfsAvailableInventory: 140,
  inboundInventory: 130,
  sales90Days: 130,
  adSpend30Days: 140,
  disabledReason: 130,
  listingStatus: 130,
  buyBoxStatus: 130,
  walmartSeller: 140,
  resold: 120,
  checkedAt: 160,
  rating: 100,
  reviewCount: 110,
  brand: 130,
  tags: 130,
  gtin: 160,
  productGrade: 120,
  archiveReason: 180,
  actions: 112,
};

const columnGroups: RuntimeColumnGroup[] = [
  { title: "Listing 管理字段", fields: [...listingColumnFields] },
];

interface ListingManagementPageProps {
  page: NavigationPage;
}


interface ListingArchiveDialogState {
  mode: "single" | "batch";
  rows: ListingManagementRow[];
}

interface ListingRestoreDialogState {
  rows: ListingManagementRow[];
}

interface ListingGptAnalysisFormValues {
  keywordAnalysisUrl: string;
  adAnalysisUrl: string;
}

function ListingManagementPage({ page }: ListingManagementPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [gptAnalysisForm] = Form.useForm<ListingGptAnalysisFormValues>();
  const [managedTags, setManagedTags] = useState<CustomProductTag[]>([]);
  const [batchTagOpen, setBatchTagOpen] = useState(false);
  const [listingRefreshToken, setListingRefreshToken] = useState(0);
  const [tagManagerOpen, setTagManagerOpen] = useState(false);
  const [isTagManagerLoading, setIsTagManagerLoading] = useState(false);
  const pageStateKey = "listing-management";
  const listingManagementPageRootRef = useRef<HTMLDivElement | null>(null);

  const [filters, setFilters] = usePageStateCache<ListingManagementFilters>(`${pageStateKey}:filters`, createInitialFilters);
  const [statisticsVisible, setStatisticsVisible] = usePageStateCache(`${pageStateKey}:statisticsVisible`, true);
  const [summaryFilterKey, setSummaryFilterKey] = usePageStateCache<ListingManagementSummaryCardKey>(
    `${pageStateKey}:summaryFilterKey:v3`,
    DEFAULT_LISTING_SUMMARY_FILTER_KEY,
  );
  const [columnConfigOpen, setColumnConfigOpen] = usePageStateCache(`${pageStateKey}:columnConfigOpen`, false);
  const [appliedColumnKeys, setAppliedColumnKeys] = usePageStateCache<string[]>(`${pageStateKey}:appliedColumnKeys`, defaultColumnKeys);
  const [columnWidths, setColumnWidths] = usePageStateCache<Record<string, number>>(`${pageStateKey}:columnWidths`, defaultColumnWidths);
  const [currentPage, setCurrentPage] = usePageStateCache(`${pageStateKey}:currentPage`, 1);
  const [pageSize, setPageSize] = usePageStateCache(`${pageStateKey}:pageSize`, REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = usePageStateCache<Key[]>(`${pageStateKey}:selectedRowKeys`, []);

  const [rows, setRows] = useState<ListingManagementRow[]>([]);
  const [archiveStateOverrides, setArchiveStateOverrides] = useState<Record<string, boolean>>({});
  const applyArchiveStateOverrides = useCallback(
    (currentRows: ListingManagementRow[]) =>
      currentRows.map((currentRow) =>
        Object.prototype.hasOwnProperty.call(archiveStateOverrides, currentRow.id)
          ? {
              ...currentRow,
              isArchived: Boolean(archiveStateOverrides[currentRow.id]),
            }
          : currentRow,
      ),
    [archiveStateOverrides],
  );

  const [totalRows, setTotalRows] = useState(0);
  const [summary, setSummary] = useState<ListingManagementSummary>(emptySummary);
  const [filterOptions, setFilterOptions] = useState<ListingManagementFilterOptions>(emptyFilterOptions);
  const [analysisSource, setAnalysisSource] = useState<ListingAnalysisSource | null>(null);
  const [gptAnalysisRow, setGptAnalysisRow] = useState<ListingManagementRow | null>(null);
  const [isGptAnalysisLoading, setIsGptAnalysisLoading] = useState(false);
  const [isGptAnalysisSaving, setIsGptAnalysisSaving] = useState(false);
  const [isTableRequesting, setIsTableRequesting] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [archiveDialog, setArchiveDialog] = useState<ListingArchiveDialogState | null>(null);
  const [archiveReason, setArchiveReason] = useState("");
  const [archiveSubmitting, setArchiveSubmitting] = useState(false);
  const [restoreDialog, setRestoreDialog] = useState<ListingRestoreDialogState | null>(null);
  const [restoreSubmitting, setRestoreSubmitting] = useState(false);

  useElementScrollRestoration(`${pageStateKey}:tableScroll`, listingManagementPageRootRef, ".ant-table-body");

  useEffect(() => {
    setAppliedColumnKeys((current) => (
      current.includes("gptAnalysis") ? current : [...current, "gptAnalysis"]
    ));
  }, [setAppliedColumnKeys]);


  const reloadListingTags = useCallback(async (options: { showError?: boolean } = {}) => {
    setIsTagManagerLoading(true);

    try {
      const tags = await fetchListingTags();
      setManagedTags(tags);
    } catch {
      setManagedTags([]);
      if (options.showError) {
        void messageApi.warning("标签加载失败，暂时不影响 Listing 页面");
      }
    } finally {
      setIsTagManagerLoading(false);
    }
  }, [messageApi]);

  const handleCreateListingTag = useCallback(
    (payload: Parameters<typeof createListingTag>[0]) => createListingTag(payload),
    [],
  );

  const handleUpdateListingTag = useCallback(
    (tagId: string, payload: Parameters<typeof updateListingTag>[1]) => updateListingTag(tagId, payload),
    [],
  );

  const handleDeleteListingTag = useCallback(
    (tagId: string) => deleteListingTag(tagId),
    [],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void reloadListingTags({ showError: false });
    }, 0);


  return () => window.clearTimeout(timer);
  }, [reloadListingTags]);

  useEffect(() => {
    if (!tagManagerOpen) return undefined;

    const timer = window.setTimeout(() => {
      void reloadListingTags({ showError: true });
    }, 0);

    return () => window.clearTimeout(timer);
  }, [reloadListingTags, tagManagerOpen]);

  const tagOptions = useMemo(() => {
    const optionMap = new Map<string, { value: string; label: string; count: number }>();

    for (const option of filterOptions.tags ?? []) {
      optionMap.set(String(option.value), {
        value: String(option.value),
        label: String(option.label ?? option.value),
        count: Number(option.count ?? 0),
      });
    }

    for (const tag of managedTags) {
      optionMap.set(tag.name, {
        value: tag.name,
        label: tag.name,
        count: tag.usage,
      });
    }

    return Array.from(optionMap.values());
  }, [filterOptions.tags, managedTags]);

  const assignmentTags = useMemo(() => managedTags, [managedTags]);

  const normalizedFilters = useMemo(() => {
    const owners = filters.owners && filters.owners.length > 0
      ? filters.owners
      : filters.owner ? [filters.owner] : [];
    const productTypes = filters.productTypes && filters.productTypes.length > 0
      ? filters.productTypes
      : filters.productType ? [filters.productType] : [];
    const productStatuses = filters.productStatuses && filters.productStatuses.length > 0
      ? filters.productStatuses
      : filters.productStatus ? [filters.productStatus] : [];

    return {
      stores: filters.stores ?? [],
      owners,
      productTypes,
      productStatuses,
      tagValues: filters.tagValues ?? [],
      archiveStatuses: filters.archiveStatuses ?? [],
      searchType: filters.searchType,
      keyword: filters.keyword,
      batchValues: filters.batchValues,
    };
  }, [filters]);

  useEffect(() => {
    let active = true;

    void fetchListingManagementFilterOptions()
      .then((options) => {
        if (!active) return;
        setFilterOptions(options);
      })
      .catch(() => {
        if (!active) return;
        setFilterOptions(emptyFilterOptions);
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    void fetchListingManagementSummary(normalizedFilters)
      .then((nextSummary) => {
        if (!active) return;
        setSummary(nextSummary);
      })
      .catch(() => {
        if (!active) return;
        setSummary(emptySummary);
      });

    return () => {
      active = false;
    };
  }, [normalizedFilters]);

  useEffect(() => {
    let active = true;

    queueMicrotask(() => {
      if (active) setIsTableRequesting(true);
    });

    void fetchListingManagementRows({
      ...normalizedFilters,
      summaryFilter: summaryFilterKey || DEFAULT_LISTING_SUMMARY_FILTER_KEY,
      page: currentPage,
      pageSize,
    })
      .then(({ rows: nextRows, meta }) => {
        if (!active) return;
        setRows(nextRows);
        setTotalRows(meta.total);
      })
      .catch(() => {
        if (!active) return;
        setRows([]);
        setTotalRows(0);
      })
      .finally(() => {
        if (active) setIsTableRequesting(false);
      });

    return () => {
      active = false;
    };
  }, [currentPage, listingRefreshToken, normalizedFilters, pageSize, summaryFilterKey]);

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const updateFilters = (nextFilters: ListingManagementFilters) => {
    setFilters(nextFilters);
    setSummaryFilterKey(DEFAULT_LISTING_SUMMARY_FILTER_KEY);
    setListingRefreshToken((current) => current + 1);
    resetPageAndSelection();
  };

  const handleSummaryCardClick = (key: ListingManagementSummaryCardKey) => {
    setSummaryFilterKey(key);
    resetPageAndSelection();
  };

  const resetFilters = () => {
    setFilters(createInitialFilters());
    setSummaryFilterKey(DEFAULT_LISTING_SUMMARY_FILTER_KEY);
    resetPageAndSelection();
  };

  const runArchiveListing = useCallback(async (row: ListingManagementRow, reason: string) => {
    try {
      const archiveResult = (await archiveListingManagementRow(row.id, reason)) as unknown as
        | {
            isArchived?: boolean;
            is_archived?: boolean;
            archiveReason?: string | null;
            archive_reason?: string | null;
            data?: {
              isArchived?: boolean;
              is_archived?: boolean;
              archiveReason?: string | null;
              archive_reason?: string | null;
            };
          }
        | undefined;

      const nextIsArchived =
        archiveResult?.data?.isArchived ??
        archiveResult?.data?.is_archived ??
        archiveResult?.isArchived ??
        archiveResult?.is_archived ??
        true;
      const nextArchiveReason =
        archiveResult?.data?.archiveReason ??
        archiveResult?.data?.archive_reason ??
        archiveResult?.archiveReason ??
        archiveResult?.archive_reason ??
        reason;

      setArchiveStateOverrides?.((current) => ({ ...current, [row.id]: Boolean(nextIsArchived) }));
      setRows((currentRows) =>
        currentRows.map((item) =>
          item.id === row.id
            ? {
                ...item,
                isArchived: Boolean(nextIsArchived),
                archiveReason: nextArchiveReason,
              }
            : item,
        ),
      );
      void messageApi.success("已归档");
    } catch {
      void messageApi.error("归档失败，请稍后重试");
    }
  }, [messageApi]);

  const handleArchiveListing = useCallback((row: ListingManagementRow) => {
    setArchiveReason("");
    setArchiveDialog({ mode: "single", rows: [row] });
  }, []);

  const handleArchiveDialogCancel = useCallback(() => {
    if (archiveSubmitting) return;
    setArchiveDialog(null);
    setArchiveReason("");
  }, [archiveSubmitting]);

  const handleArchiveDialogOk = useCallback(async () => {
    const reason = archiveReason.trim();

    if (reason.length < 2) {
      void messageApi.warning("归档原因至少需要 2 个字");
      return;
    }

    const targetRows = archiveDialog?.rows ?? [];
    if (targetRows.length === 0) {
      setArchiveDialog(null);
      setArchiveReason("");
      return;
    }

    setArchiveSubmitting(true);

    try {
      if (archiveDialog?.mode === "single") {
        await runArchiveListing(targetRows[0], reason);
      } else {
        const results = await Promise.allSettled(
          targetRows.map((row) => archiveListingManagementRow(row.id, reason)),
        );
        const succeededIds = new Set(
          targetRows
            .filter((_, index) => results[index]?.status === "fulfilled")
            .map((row) => row.id),
        );

        setRows((currentRows) =>
          currentRows.map((row) =>
            succeededIds.has(row.id)
              ? {
                  ...row,
                  isArchived: true,
                  archiveReason: reason,
                }
              : row,
          ),
        );

        setSelectedRowKeys([]);
        setListingRefreshToken((current) => current + 1);

        const failed = results.length - succeededIds.size;
        if (failed > 0) {
          void messageApi.warning(`批量归档完成：成功 ${succeededIds.size} 个，失败 ${failed} 个`);
        } else {
          void messageApi.success(`已归档 ${succeededIds.size} 个 Listing`);
        }
      }

      setArchiveDialog(null);
      setArchiveReason("");
    } catch {
      void messageApi.error("归档失败，请稍后重试");
    } finally {
      setArchiveSubmitting(false);
    }
  }, [
    archiveDialog,
    archiveReason,
    messageApi,
    runArchiveListing,
    setSelectedRowKeys,
  ]);

  const handleRestoreListing = useCallback(async (row: ListingManagementRow) => {
    try {
      const restoreResult = (await restoreListingManagementRow(row.id)) as unknown as
        | {
            isArchived?: boolean;
            is_archived?: boolean;
            data?: { isArchived?: boolean; is_archived?: boolean };
          }
        | undefined;
      const nextIsArchived =
        restoreResult?.data?.isArchived ??
        restoreResult?.data?.is_archived ??
        restoreResult?.isArchived ??
        restoreResult?.is_archived ??
        false;
      setArchiveStateOverrides((current) => ({ ...current, [row.id]: nextIsArchived }));
      setRows((current) => current.map((item) => (
        item.id === row.id ? { ...item, isArchived: nextIsArchived } : item
      )));
      setListingRefreshToken((current) => current + 1);
      void messageApi.success("已恢复");
    } catch {
      void messageApi.error("恢复失败，请稍后重试");
    }
  }, [messageApi]);

  const handleExportListingRows = useCallback(async (columnKeys?: string[]) => {
    if (isExporting) return;

    setIsExporting(true);
    const closeLoading = messageApi.loading("正在导出 Listing 数据，请稍候", 0);

    try {
      await exportListingManagementRows(
        {
          ...normalizedFilters,
          summaryFilter: summaryFilterKey || DEFAULT_LISTING_SUMMARY_FILTER_KEY,
        },
        columnKeys,
      );
      closeLoading();
      setExportModalOpen(false);
      void messageApi.success("Listing 导出已开始下载");
    } catch {
      closeLoading();
      void messageApi.error("Listing 导出失败，请稍后重试");
    } finally {
      setIsExporting(false);
    }
  }, [isExporting, messageApi, normalizedFilters, summaryFilterKey]);

  const openExportModal = useCallback(() => {
    if (isExporting) return;
    setExportModalOpen(true);
  }, [isExporting]);

  const closeExportModal = useCallback(() => {
    if (isExporting) return;
    setExportModalOpen(false);
  }, [isExporting]);

  const openListingAnalysis = (row: ListingManagementRow) => {
    setAnalysisSource({
      title: row.title || row.productName,
      sku: row.sku,
      msku: row.msku,
      productId: row.productId,
      date: row.listedAt || row.checkedAt,
      platform: "Walmart US",
      status: row.listingStatus || row.productStatus,
      store: row.store,
      listPrice: row.listPrice,
      salePrice: row.salePrice,
      rating: row.rating,
      reviewCount: row.reviewCount,
      wfsAvailableInventory: row.wfsAvailableInventory,
    });
  };

  const openGptAnalysisModal = useCallback((row: ListingManagementRow) => {
    setGptAnalysisRow(row);
    gptAnalysisForm.setFieldsValue({
      keywordAnalysisUrl: "",
      adAnalysisUrl: "",
    });
    setIsGptAnalysisLoading(true);

    void fetchListingGptAnalysisLink(row.id)
      .then((data) => {
        gptAnalysisForm.setFieldsValue({
          keywordAnalysisUrl: data.keywordAnalysisUrl,
          adAnalysisUrl: data.adAnalysisUrl,
        });
      })
      .catch(() => {
        void messageApi.warning("GPT分析链接加载失败，可重新填写后保存");
      })
      .finally(() => setIsGptAnalysisLoading(false));
  }, [gptAnalysisForm, messageApi]);

  const closeGptAnalysisModal = useCallback(() => {
    setGptAnalysisRow(null);
    gptAnalysisForm.resetFields();
  }, [gptAnalysisForm]);

  const saveGptAnalysisLinks = useCallback(async () => {
    if (!gptAnalysisRow) return;

    try {
      const values = await gptAnalysisForm.validateFields();
      setIsGptAnalysisSaving(true);
      await saveListingGptAnalysisLink(gptAnalysisRow.id, {
        keywordAnalysisUrl: values.keywordAnalysisUrl ?? "",
        adAnalysisUrl: values.adAnalysisUrl ?? "",
      });
      void messageApi.success("GPT分析链接已保存");
      closeGptAnalysisModal();
    } catch (error) {
      if (typeof error === "object" && error !== null && "errorFields" in error) return;
      void messageApi.error("GPT分析链接保存失败，请稍后重试");
    } finally {
      setIsGptAnalysisSaving(false);
    }
  }, [closeGptAnalysisModal, gptAnalysisForm, gptAnalysisRow, messageApi]);


  const selectedListingRows = useMemo(() => {
    const selectedIds = new Set(selectedRowKeys.map(String));
    return rows.filter((row) => selectedIds.has(row.id));
  }, [rows, selectedRowKeys]);

  const handleBatchArchiveListings = useCallback(() => {
    if (selectedListingRows.length === 0) {
      void messageApi.warning("请先选择 Listing");
      return;
    }

    setArchiveReason("");
    setArchiveDialog({ mode: "batch", rows: selectedListingRows });
  }, [messageApi, selectedListingRows]);

  const handleBatchRestoreListings = useCallback(() => {
    if (selectedListingRows.length === 0) {
      void messageApi.warning("请先选择 Listing");
      return;
    }

    setRestoreDialog({ rows: selectedListingRows });
  }, [messageApi, selectedListingRows]);

  const handleRestoreDialogCancel = useCallback(() => {
    if (restoreSubmitting) return;
    setRestoreDialog(null);
  }, [restoreSubmitting]);

  const handleRestoreDialogOk = useCallback(async () => {
    const targetRows = restoreDialog?.rows ?? [];

    if (targetRows.length === 0) {
      setRestoreDialog(null);
      return;
    }

    setRestoreSubmitting(true);

    try {
      const results = await Promise.allSettled(
        targetRows.map((row) => restoreListingManagementRow(row.id)),
      );
      const succeededIds = new Set(
        targetRows
          .filter((_, index) => results[index]?.status === "fulfilled")
          .map((row) => row.id),
      );

      setRows((currentRows) =>
        currentRows.map((row) =>
          succeededIds.has(row.id)
            ? {
                ...row,
                isArchived: false,
              }
            : row,
        ),
      );

      setSelectedRowKeys([]);
      setListingRefreshToken((current) => current + 1);

      const failed = results.length - succeededIds.size;
      if (failed > 0) {
        void messageApi.warning(`批量恢复完成：成功 ${succeededIds.size} 个，失败 ${failed} 个`);
      } else {
        void messageApi.success(`已恢复 ${succeededIds.size} 个 Listing`);
      }

      setRestoreDialog(null);
    } catch {
      void messageApi.error("批量恢复失败，请稍后重试");
    } finally {
      setRestoreSubmitting(false);
    }
  }, [messageApi, restoreDialog, setSelectedRowKeys]);


  return (
    <PageShell page={page}>
      {messageContextHolder}
      <div ref={listingManagementPageRootRef} className="listing-management">
        <Card size="small" className="listing-management__page-card">
          <RequestLoadingOverlay spinning={isTableRequesting} label="正在加载Listing数据，请稍候" />
          <div className="listing-management__title-row">
            <div>
              <h1>Listing管理</h1>
              <p>覆盖店铺、负责人、状态、价格、库存、购物车、跟卖与检查信息。</p>
            </div>
          </div>

          <Card size="small" className="listing-management__toolbar-card">
            <ListingManagementToolbar
              filters={filters}
              stores={filterOptions.stores}
              owners={filterOptions.owners}
              productTypes={filterOptions.productTypes}
              tags={tagOptions}
              archiveStatuses={filterOptions.archiveStatuses}
              statisticsVisible={statisticsVisible}
              onChange={updateFilters}
              onReset={resetFilters}
              onBatchSearch={(values) => updateFilters({ ...filters, batchValues: values })}
              onMessage={(content) => void messageApi.info(content)}
              onToggleStatistics={() => setStatisticsVisible((visible) => !visible)}
              onOpenTagManager={() => setTagManagerOpen(true)}
              onOpenColumnConfig={() => setColumnConfigOpen(true)}
              onDownload={openExportModal}
              downloadDisabled={isExporting}
              downloadLoading={isExporting}
            />
          </Card>

          {statisticsVisible && (
            <ListingManagementSummaryCards
              summary={summary}
              activeKey={summaryFilterKey}
              onCardClick={handleSummaryCardClick}
            />
          )}

          <div className="listing-management__table-wrap">
            <ListingManagementTable
              rows={applyArchiveStateOverrides(rows)}
              total={totalRows}
              appliedColumnKeys={appliedColumnKeys}
              columnWidths={columnWidths}
              currentPage={currentPage}
              pageSize={pageSize}
              selectedRowKeys={selectedRowKeys}
              onColumnWidthChange={(key, width) => setColumnWidths((current) => ({
                ...current,
                [key]: width,
              }))}
              onCurrentPageChange={setCurrentPage}
              onPageSizeChange={(nextPageSize) => {
                setPageSize(normalizeReportTablePageSize(nextPageSize));
                resetPageAndSelection();
              }}
              onSelectionChange={setSelectedRowKeys}
              onOpenDetail={openListingAnalysis}
              onOpenGptAnalysis={openGptAnalysisModal}
              onArchiveListing={(row) => void handleArchiveListing(row)}
              onRestoreListing={(row) => void handleRestoreListing(row)}
              onBatchArchive={handleBatchArchiveListings}
              onBatchRestore={handleBatchRestoreListings}
              onBatchSetTags={() => {
                if (selectedRowKeys.length === 0) {
                  void messageApi.warning("请先选择商品");
                  return;
                }
                setBatchTagOpen(true);
              }}
              onBulkExport={openExportModal}
              exporting={isExporting}
            />
          </div>
        </Card>

        <ListExportModal
          open={exportModalOpen}
          title="导出数据"
          subtitle="配置导出字段"
          columnGroups={listingExportColumnGroups}
          defaultSelectedColumnKeys={listingDefaultExportColumnKeys}
          exporting={isExporting}
          onClose={closeExportModal}
          onExport={handleExportListingRows}
        />

        <RuntimeColumnConfigDrawer
          open={columnConfigOpen}
          groups={columnGroups}
          fixedKeys={fixedListingColumnKeys}
          defaultKeys={defaultColumnKeys}
          appliedKeys={appliedColumnKeys}
          onApply={setAppliedColumnKeys}
          onClose={() => setColumnConfigOpen(false)}
          onSaveTemplate={() => void messageApi.info(TEMPLATE_PENDING)}
        />
        <Modal
          open={gptAnalysisRow !== null}
          title={gptAnalysisRow ? `GPT分析：${gptAnalysisRow.productId}` : "GPT分析"}
          okText="保存"
          cancelText="取消"
          confirmLoading={isGptAnalysisSaving}
          onOk={() => void saveGptAnalysisLinks()}
          onCancel={closeGptAnalysisModal}
          destroyOnHidden
        >
          <div className="listing-management__gpt-analysis-meta">
            <span>{gptAnalysisRow?.productName ?? "-"}</span>
            <small>{gptAnalysisRow?.sku ?? "-"} / {gptAnalysisRow?.msku ?? "-"}</small>
          </div>
          <Form<ListingGptAnalysisFormValues>
            form={gptAnalysisForm}
            layout="vertical"
            disabled={isGptAnalysisLoading || isGptAnalysisSaving}
          >
            <Form.Item
              name="keywordAnalysisUrl"
              label="关键词分析链接"
              rules={[{ max: 2048, message: "链接不能超过 2048 个字符" }]}
            >
              <Input allowClear placeholder="粘贴关键词分析链接" />
            </Form.Item>
            <Form.Item
              name="adAnalysisUrl"
              label="广告分析链接"
              rules={[{ max: 2048, message: "链接不能超过 2048 个字符" }]}
            >
              <Input allowClear placeholder="粘贴广告分析链接" />
            </Form.Item>
          </Form>
        </Modal>
        <ListingAnalysisModal
          open={analysisSource !== null}
          source={analysisSource ?? undefined}
          onClose={() => setAnalysisSource(null)}
        />
      </div>
        <ProductTagAssignmentModal
          open={batchTagOpen}
          selectedProductCount={selectedRowKeys.length}
          tags={assignmentTags}
          loading={isTagManagerLoading}
          onCancel={() => setBatchTagOpen(false)}
          onConfirm={(selectedTags) => {
            if (selectedRowKeys.length === 0) {
              void messageApi.warning("请先选择商品");
              return;
            }
            if (selectedTags.length === 0) {
              void messageApi.warning("请选择标签");
              return;
            }

            void batchSetListingTags({
              listingIds: selectedRowKeys.map(String),
              tagValues: selectedTags,
              mode: "append",
            })
              .then(() => {
                void messageApi.success(`已给 ${selectedRowKeys.length} 个商品添加标签`);
                setBatchTagOpen(false);
                setSelectedRowKeys([]);
                setListingRefreshToken((current) => current + 1);
                void reloadListingTags({ showError: false });
              })
              .catch(() => {
                void messageApi.error("设置标签失败，请确认后端接口已接入");
              });
          }}
        />
        <CustomTagManagerModal
          open={tagManagerOpen}
          initialTags={managedTags}
          loading={isTagManagerLoading}
          onCreateTag={handleCreateListingTag}
          onUpdateTag={handleUpdateListingTag}
          onDeleteTag={handleDeleteListingTag}
          onTagsChange={setManagedTags}
          onClose={() => setTagManagerOpen(false)}
        />
        <Modal
          title={archiveDialog?.mode === "batch"
            ? `批量归档 ${archiveDialog.rows.length} 个 Listing`
            : "填写归档原因"}
          open={archiveDialog !== null}
          okText={archiveDialog?.mode === "batch" ? "确认批量归档" : "确认归档"}
          cancelText="取消"
          confirmLoading={archiveSubmitting}
          maskClosable={!archiveSubmitting}
          destroyOnHidden
          onCancel={handleArchiveDialogCancel}
          onOk={() => void handleArchiveDialogOk()}
        >
          <div className="listing-management__archive-modal">
            <div className="listing-management__archive-modal-label">归档原因</div>
            <Input.TextArea
              autoFocus
              rows={4}
              maxLength={200}
              showCount
              value={archiveReason}
              placeholder="请输入归档原因，例如：暂停运营、重复 Listing、异常数据、暂不推广等"
              onChange={(event) => setArchiveReason(event.target.value)}
            />
          </div>
        </Modal>

        <Modal
          title={`批量恢复 ${restoreDialog?.rows.length ?? 0} 个 Listing`}
          open={restoreDialog !== null}
          okText="确认恢复"
          cancelText="取消"
          confirmLoading={restoreSubmitting}
          maskClosable={!restoreSubmitting}
          destroyOnHidden
          onCancel={handleRestoreDialogCancel}
          onOk={() => void handleRestoreDialogOk()}
        >
          <p>恢复后这些 Listing 会重新回到正常状态。</p>
        </Modal>
    </PageShell>
  );
}

export default ListingManagementPage;

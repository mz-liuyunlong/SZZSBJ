import { useState as useLifecycleEditState } from "react";
import { Select } from "antd";
import { RobotOutlined, InfoCircleOutlined } from "@ant-design/icons";
import {
  Button,
  Space,
  Tag,
  Popconfirm,
  Tooltip,
  Popover,
} from "antd"; import { ProTable,
  type ProColumns } from "@ant-design/pro-components"; import type { Key } from "react"; import ReportTableShell,
  {   ReportTableSelectionBar,
  } from "@/components/report-table/ReportTableShell"; import {   REPORT_TABLE_PAGE_SIZE_OPTIONS,
  } from "@/components/report-table/pagination"; import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle"; import { ImageCell,
  ProductIdentityCell,
  SkuMskuIdentityCell,
  CopyableTextCell,
} from "@/components/report-table/cells";
import {
  listingColumnFields,
  type ListingManagementRow,
  listingLifecycleOptions,
} from "@/pages/products/listingManagementData";

// LISTING_LAYOUT_20261104_V2: header-only QA marks are enabled in acceptance worktree.
const listingLayoutQaHintsEnabled = false;
const listingLayoutQaTips: Record<string, string> = {
  "storeOwner": "\u5e97\u94fa\u548c\u8d1f\u8d23\u4eba\u5408\u5e76\u4e3a\u4e00\u5217\uff0c\u786e\u8ba4\u4e0a\u4e0b\u4e24\u884c\u5747\u6b63\u786e",
  "imageCount": "\u56fe\u7247\u6570\u91cf\u5e94\u6765\u81ea\u6700\u8fd1\u6210\u529f\u76d1\u63a7\u7684RAW\uff1b0\u548c\u7f3a\u5931\u503c\u987b\u533a\u5206",
  "listPrice": "\u76d1\u63a7\u5212\u7ebf\u4ef7\u4f18\u5148\uff1b\u786e\u8ba4\u65e0\u5212\u7ebf\u4ef7\u4e0d\u5f97\u88ab\u65e7\u503c\u515c\u5e95",
  "hasStrikethrough": "\u76d1\u63a7true/false/null\u5e94\u5206\u522b\u663e\u793a\u6709/\u65e0/\u5f85\u68c0\u6d4b",
  "salePrice": "\u76d1\u63a7\u552e\u4ef7\u4f18\u5148\uff0c\u672a\u53d6\u5230\u65f6\u624d\u4f7f\u7528\u9886\u661f\u503c",
  "productGrade": "\u4ec5\u4fee\u6539\u5217\u540d\u4e3alisting\u7b49\u7ea7\uff0c\u4e0d\u6539\u53d8\u8bc4\u7ea7\u7b97\u6cd5",
  "buyBoxStatus": "RAW cartStatus=NORMAL\u8868\u793a\u8d2d\u4e70\u6846\u6b63\u5e38\uff0c\u4e0d\u7b49\u4e8e\u672c\u5e97\u62e5\u6709Buy Box",
  "sellerOfferCount": "\u5356\u5bb6\u6570\u91cf\u53d6\u81eaRAW sellerOfferCount",
  "sellerNames": "\u5356\u5bb6\u5217\u8868\u53d6\u81eaRAW sellerNames\uff0c\u786e\u4fdd\u957f\u540d\u79f0\u53ef\u5b8c\u6574\u67e5\u770b",
  "resold": "\u8ddf\u5356\u72b6\u6001\u8981\u533a\u5206\u662f/\u5426/\u5f85\u68c0\u6d4b\uff0c\u5e76\u6838\u5bf9\u76d1\u63a7\u5356\u5bb6\u8bc1\u636e",
  "checkedAt": "\u4f7f\u7528\u6700\u8fd1\u6210\u529f\u76d1\u63a7\u65f6\u95f4\uff0c\u53ea\u663e\u793a\u5e74-\u6708-\u65e5\uff0c\u4e0d\u662f\u6570\u636e\u5237\u65b0\u65f6\u95f4",
  "rating": "\u8bc4\u5206\u7f3a\u5931\u4e0d\u663e\u793a\u4e3a0",
  "reviewCount": "\u8bc4\u8bba\u6570\u7f3a\u5931\u4e0d\u663e\u793a\u4e3a0",
  "keyFeatures": "\u4e94\u70b9\u63cf\u8ff0\u6765\u81eaRAW keyFeatures\uff0c\u53ef\u5b8c\u6574\u67e5\u770b\u6570\u7ec4\u5185\u5bb9"
};

/** Match the observed two-line Listing row height without changing its visual size. */
const LISTING_VIRTUAL_ROW_HEIGHT_ESTIMATE = 61;

const minColumnWidths: Record<string, number> = {
  image: 72,
  productIdName: 240,
  skuMsku: 190,
  msku: 130,
  productId: 150,
  storeOwner: 172,
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
  sellerOfferCount: 120,
  sellerNames: 170,
  hasStrikethrough: 130,
  strikethroughSource: 150,
  imageCount: 110,
  imageUrls: 140,
  keyFeatures: 140,
  reviewFetchStatus: 130,
  tags: 130,
  productTags: 180,
  gtin: 160,
  productGrade: 120,
  archiveReason: 180,
  actions: 132,
};

const statusColorMap: Record<string, string> = {
  启用: "green",
  停用: "red",
  在线: "green",
  离线: "red",
  拥有: "green",
  未拥有: "orange",
  是: "orange",
  否: "default",
  正常: "green",
  异常: "red",
  购物车丢失: "red",
  未拥有购物车: "orange",
  未找到购物车: "orange",
  缺货: "orange",
  不可购买: "red",
  待确认: "default",
  检测失败: "default",
};

interface ListingManagementTableProps {
  rows: ListingManagementRow[];
  total: number;
  appliedColumnKeys: string[];
  columnWidths: Record<string, number>;
  currentPage: number;
  pageSize: number;
  virtualScrollY?: number;
  selectedRowKeys: Key[];
  onColumnWidthChange: (key: string, width: number) => void;
  onCurrentPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onSelectionChange: (keys: Key[]) => void;
  onOpenDetail: (row: ListingManagementRow) => void;
  onOpenGptAnalysis?: (row: ListingManagementRow) => void;
  onArchiveListing?: (row: ListingManagementRow) => void;
  onRestoreListing?: (row: ListingManagementRow) => void;
  onBatchSetTags: () => void;
  onBatchArchive?: () => void;
  onBatchRestore?: () => void;
  onBulkExport: () => void;
  onSetLifecycle?: (row: ListingManagementRow, stage: string) => Promise<boolean>;
  onBatchEditLifecycle?: () => void;
  lifecycleSaving?: boolean;
  exporting?: boolean;
}

// LIFECYCLE_INLINE_CONFIRM_20261105: pending selection is NOT committed before confirmation.
function LifecycleStageSelect({
  row,
  disabled,
  onSave,
}: {
  row: ListingManagementRow;
  disabled: boolean;
  onSave?: (row: ListingManagementRow, stage: string) => Promise<boolean>;
}) {
  const [pendingStage, setPendingStage] = useLifecycleEditState<string | null>(null);
  const [submitting, setSubmitting] = useLifecycleEditState(false);
  const committedStage = listingLifecycleOptions.some((option) => option.value === row.lifecycle)
    ? row.lifecycle
    : undefined;

  const resetSelection = () => {
    if (!submitting) setPendingStage(null);
  };

  const confirmChange = async () => {
    const stage = pendingStage;
    if (!stage || disabled || !onSave) {
      setPendingStage(null);
      return;
    }
    setSubmitting(true);
    try {
      await onSave(row, stage);
    } finally {
      // On success the page updates the committed row. On failure, show the old value.
      setSubmitting(false);
      setPendingStage(null);
    }
  };

  return (
    <Popconfirm
      title="确认修改生命周期？"
      description={`${row.productId}：${row.lifecycle || "待判定"} → ${pendingStage ?? ""}`}
      okText="确认修改"
      cancelText="取消"
      okButtonProps={{ loading: submitting }}
      placement="top"
      open={pendingStage !== null}
      onOpenChange={(open) => {
        if (!open) resetSelection();
      }}
      onConfirm={() => void confirmChange()}
      onCancel={resetSelection}
    >
      <span style={{ flex: "1 1 0", minWidth: 0, display: "block" }}>
        <Select
          size="small"
          variant="borderless"
          aria-label={`修改 ${row.productId} 生命周期`}
          value={pendingStage ?? committedStage}
          placeholder="待判定"
          options={[...listingLifecycleOptions]}
          disabled={disabled || submitting || !onSave}
          popupMatchSelectWidth={false}
          onChange={(stage) => {
            if (stage === row.lifecycle) {
              setPendingStage(null);
            } else {
              setPendingStage(stage);
            }
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") resetSelection();
          }}
          style={{ width: "100%", minWidth: 0 }}
        />
      </span>
    </Popconfirm>
  );
}

// LIFECYCLE_COMPACT_REASON_20261105: operational wording, concise evidence, no raw codes.
const LIFECYCLE_REASON_WORDING: Record<string, { title: string; why: string; next: string }> = {
  // LIFECYCLE_UI_INVENTORY_ONLY_V1: legacy/stale code never means "not WFS".
  NON_WFS_NOT_ELIGIBLE: {
    title: "WFS库存证据需刷新",
    why: "历史试算结果未包含该商品的WFS每日库存记录，不能据此否认它有WFS库存。",
    next: "刷新试算，核对WFS每日库存是否有正库存记录。",
  },
  WFS_DAILY_HISTORY_MISSING: {
    title: "WFS每日库存记录不足",
    why: "商品显示有WFS库存，但历史每日快照尚未核实，暂不判断阶段。",
    next: "核对WFS库存同步记录及计算截止日期。",
  },
  PREVIEW_NOT_AVAILABLE: {
    title: "尚未获取判定数据",
    why: "当前还没有取得这件商品的最新计算记录。",
    next: "请检查正式诊断接口是否已启用，或稍后刷新页面。",
  },
  WORKFLOW_PROTECTED: {
    title: "已由业务流程管理",
    why: "商品已归档，或处于需要人工处理的业务阶段。",
    next: "如需调整，请先通过对应的业务流程处理。",
  },
  PERSISTED_STAGE_PROTECTED: {
    title: "已保存生命周期",
    why: "该商品已有正式保存的生命周期，自动结果不会覆盖。",
    next: "如需更改，请使用生命周期编辑功能。",
  },
  NO_POSITIVE_WFS_HISTORY: {
    title: "缺少有货记录",
    why: "历史记录中没有找到 WFS 库存大于零的日期。",
    next: "检查库存同步是否完整，以及商品与库存记录是否对应。",
  },
  TREND_CONFIRMED: {
    title: "已满足阶段判定条件",
    why: "现有销量、库存或监控记录符合当前的生命周期规则。",
    next: "当前显示只读诊断，只有正式发布流程才会修改已保存状态。",
  },
  CUTOFF_WFS_MISSING: {
    title: "当天库存记录缺失",
    why: "计算截止日没有获取到 WFS 可售库存，无法确定商品状态。",
    next: "检查当天的 WFS 库存同步。缺失不等于库存为零。",
  },
  STOCKOUT_EVIDENCE_INCOMPLETE: {
    title: "断货天数还不够",
    why: "当前库存为零，但连续低库存的记录尚未达到断货门槛。",
    next: "继续同步每日库存，满足连续天数后再自动判定。",
  },
  LOW_STOCK_STREAK_INCOMPLETE: {
    title: "低库存观察天数不足",
    why: "当前库存较低，但尚不能确定已达到连续断货标准。",
    next: "继续观察每日库存，暂不直接判为断货。",
  },
  SALES_IDENTITY_CONFLICT: {
    title: "部分销量记录无法合计",
    why: "同一天的部分 MSKU 记录无法安全合并，影响销量趋势判断。",
    next: "检查重复或缺失的 MSKU 标识，确认实际销量。",
  },
  HISTORICAL_LAUNCH_UNVERIFIED: {
    title: "首次有货日期未确认",
    why: "只能找到历史上最早的一次有货记录，不能确定那天就是首次有货。",
    next: "核实首次有货记录；已有充分趋势数据时仍可判定其他阶段。",
  },
  SALES_VALID_DAYS_INSUFFICIENT: {
    title: "可用销量天数不足",
    why: "能同时确认销量与库存的日期还不够，暂时无法判断趋势。",
    next: "检查每日销量和库存同步，不要把缺失日期当作零销量。",
  },
  TREND_NOT_CONFIRMED: {
    title: "销量趋势暂不明确",
    why: "虽有销量记录，但还不满足上升、稳定或下滑的判定条件。",
    next: "继续积累数据，或在规则配置中检查趋势阈值。",
  },
  MONITOR_EVIDENCE_MISSING: {
    title: "监控记录不足",
    why: "近期缺少有效的价格或购物车监控记录。",
    next: "检查监控任务；这不一定影响销量趋势的判断。",
  },
  OTHER_EVIDENCE_INCOMPLETE: {
    title: "暂时无法判定",
    why: "已有部分数据，但还不满足安全判定的条件。",
    next: "检查每日库存、销量和监控记录是否完整。",
  },
};

const LIFECYCLE_EVIDENCE_LABELS: Record<string, string> = {
  "截止日WFS可售": "当前可售库存",
  "Listing当前WFS库存": "页面WFS库存",
  "近30天有效库存": "有库存记录",
  "近30天有效销量日": "可用销量天数",
  "四周销量有效天数（早→近）": "近4周可用天数",
  "当前连续低库存": "连续低库存",
  "历史首次有货观测": "最早观察到有货",
  "近30天有效监控日": "有效监控记录",
};

// Do not invent fractional "pieces": 0.0000 -> 0 件; non-integer pieces -> data anomaly.
const displayLifecycleEvidenceValue = (label: string, raw: string): string => {
  if (label === "截止日WFS可售" || label === "Listing当前WFS库存") {
    const matched = /^\s*(-?\d+(?:\.\d+)?)\s*件\s*$/.exec(raw);
    if (matched) {
      const qty = Number(matched[1]);
      return Number.isSafeInteger(qty) ? `${qty.toLocaleString("zh-CN")} 件` : "库存数量异常，请核对";
    }
    return raw === "缺失" ? "暂无数据" : raw;
  }
  if (label === "四周销量有效天数（早→近）" && /^\d+(?:\/\d+){3}$/.test(raw)) {
    return `${raw.replace(/\//g, "、")} 天`;
  }
  return raw.replace(/(\d+)\/(\d+)天/g, "$1 / $2 天");
};

function LifecycleDiagnosticCard({
  diagnostic,
}: {
  diagnostic: NonNullable<ListingManagementRow["lifecycleDiagnostic"]>;
}) {
  const main = diagnostic.reasons[0];
  const primary = LIFECYCLE_REASON_WORDING[main?.code ?? ""] ?? {
    title: "暂时无法判定",
    why: "当前记录还不足以确定生命周期。",
    next: "检查数据采集和当前规则配置。",
  };
  const otherReasons = diagnostic.reasons.slice(1);
  const dailyEvidenceMissing = main?.code === "WFS_DAILY_HISTORY_MISSING";
  const stockRelated = ["STOCKOUT_EVIDENCE_INCOMPLETE", "LOW_STOCK_STREAK_INCOMPLETE", "CUTOFF_WFS_MISSING"].includes(main?.code ?? "");
  const trendRelated = main?.code === "TREND_CONFIRMED" || main?.code === "TREND_NOT_CONFIRMED" || main?.code === "SALES_VALID_DAYS_INSUFFICIENT";
  const preferred = dailyEvidenceMissing
    ? ["Listing当前WFS库存", "截止日WFS可售", "近30天有效库存", "历史首次有货观测"]
    : stockRelated
    ? ["截止日WFS可售", "当前连续低库存", "近30天有效库存", "近30天有效销量日"]
    : trendRelated
      ? ["近30天有效销量日", "四周销量有效天数（早→近）", "截止日WFS可售", "近30天有效库存"]
      : ["截止日WFS可售", "历史首次有货观测", "近30天有效销量日", "近30天有效库存"];
  const evidence = preferred.flatMap((label) => {
    const match = diagnostic.evidence.find((row) => row.label === label);
    return match ? [match] : [];
  });
  return (
    <div style={{ width: 300, maxHeight: 370, overflowY: "auto", fontSize: 12, lineHeight: 1.55 }}>
      <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>{diagnostic.candidateStage ? `候选：${diagnostic.candidateStage}（诊断）` : primary.title}</div>
      <div style={{ color: "#555", marginBottom: 10 }}>{primary.why}</div>
      <div style={{ background: "#f4f8ff", padding: "8px 10px", borderRadius: 6, marginBottom: 10 }}>
        <span style={{ color: "#1677ff", fontWeight: 600 }}>下一步：</span>
        <span>{primary.next}</span>
      </div>
      {evidence.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>关键数据</div>
          {evidence.map((entry) => (
            <div key={entry.label} style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10, padding: "3px 0" }}>
              <span style={{ color: "#777", minWidth: 0 }}>{LIFECYCLE_EVIDENCE_LABELS[entry.label] ?? entry.label}</span>
              <span style={{ textAlign: "right", flexShrink: 0, fontWeight: 500, fontVariantNumeric: "tabular-nums" }}>
                {displayLifecycleEvidenceValue(entry.label, entry.value)}
              </span>
            </div>
          ))}
          {trendRelated && <div style={{ color: "#999", fontSize: 11, marginTop: 3 }}>可用销量天数：当天有销量记录，且库存高于低库存门槛；四周按由早到近排列。</div>}
        </div>
      )}
      {otherReasons.length > 0 && (
        <details style={{ borderTop: "1px solid #eee", paddingTop: 7, marginTop: 7 }}>
          <summary style={{ color: "#555", cursor: "pointer", fontWeight: 500 }}>其他需要留意（{otherReasons.length}项）</summary>
          <div style={{ padding: "5px 0 0 8px", color: "#777" }}>
            {otherReasons.map((reason, index) => (
              <div key={`${reason.code}-${index}`} style={{ marginTop: 4 }}>
                · {LIFECYCLE_REASON_WORDING[reason.code]?.title ?? reason.title}
              </div>
            ))}
          </div>
        </details>
      )}
      {(diagnostic.cutoffLa || diagnostic.ruleVersion > 0) && (
        <div style={{ borderTop: "1px solid #eee", paddingTop: 7, marginTop: 9, color: "#999", fontSize: 11 }}>
          {diagnostic.cutoffLa ? `数据截止：${diagnostic.cutoffLa}（美国西部）` : ""}
          {diagnostic.ruleVersion > 0 ? ` · 规则 V${diagnostic.ruleVersion}` : ""}
        </div>
      )}
    </div>
  );
}

function ListingManagementTable({
  rows,
  total,
  appliedColumnKeys,
  columnWidths,
  currentPage,
  pageSize,
  virtualScrollY = 360,
  selectedRowKeys,
  onColumnWidthChange,
  onCurrentPageChange,
  onPageSizeChange,
  onSelectionChange,
  onOpenDetail,
  onOpenGptAnalysis,
  onArchiveListing,
  onRestoreListing,
  onBatchSetTags,
  onBatchArchive,
  onBatchRestore,
  onBulkExport,
  onSetLifecycle,
  onBatchEditLifecycle,
  lifecycleSaving = false,
  exporting = false,
}: ListingManagementTableProps) {
  // Only the large pages need row virtualization. Original columns, pinned columns,
  // sorters, selection and all per-row actions are kept unchanged in both modes.
  const virtual = pageSize >= 500;
  const title = (key: string, label: string) => (
    <>
      <ResizableColumnTitle
        label={label}
        minWidth={minColumnWidths[key] ?? 96}
        width={columnWidths[key] ?? minColumnWidths[key] ?? 112}
        onWidthChange={(width) => onColumnWidthChange(key, width)}
      />
      {listingLayoutQaHintsEnabled && listingLayoutQaTips[key] ? (
        <Tooltip title={listingLayoutQaTips[key]}>
          <span
            aria-label="QA acceptance check"
            style={{ color: "#B45309", fontSize: 11, marginLeft: 3, cursor: "help" }}
          >{"\u9a8c"}</span>
        </Tooltip>
      ) : null}
    </>
  );

  const headerCell = () => ({
    className: "report-table-resizable-header-cell",
  });

  const fieldTitle = Object.fromEntries(listingColumnFields.map((field) => [field.key, field.title]));

  const allColumns: Record<string, ProColumns<ListingManagementRow>> = {
    image: {
      key: "image",
      dataIndex: "image",
      title: title("image", fieldTitle.image),
      width: columnWidths.image,
      fixed: "left",
      onHeaderCell: headerCell,
      render: (_, row) => (
        <ImageCell
          image={row.image}
          label={`Listing 图片：${row.productName}`}
          placement="right"
        />
      ),
    },
    productIdName: {
      key: "productIdName",
      title: title("productIdName", fieldTitle.productIdName ?? "商品ID/品名"),
      width: columnWidths.productIdName,
      fixed: "left",
      sorter: (a, b) => a.productId.localeCompare(b.productId),
      onHeaderCell: headerCell,
      render: (_, row) => (
        <ProductIdentityCell
          productId={row.productId}
          productName={row.productName}
        />
      ),
    },
    skuMsku: {
      key: "skuMsku",
      title: title("skuMsku", fieldTitle.skuMsku ?? "SKU/MSKU"),
      width: columnWidths.skuMsku,
      fixed: "left",
      sorter: (a, b) => (
        a.sku.localeCompare(b.sku)
        || a.msku.localeCompare(b.msku)
      ),
      onHeaderCell: headerCell,
      render: (_, row) => (
        <SkuMskuIdentityCell
          sku={row.sku}
          msku={row.msku}
        />
      ),
    },
    msku: {
      key: "msku",
      dataIndex: "msku",
      title: title("msku", fieldTitle.msku),
      width: columnWidths.msku,
      fixed: "left",
      sorter: (a, b) => a.msku.localeCompare(b.msku),
      onHeaderCell: headerCell,
      render: (_, row) => (
        <CopyableTextCell
          text={row.msku}
          label="MSKU"
          link
          onOpen={() => onOpenDetail(row)}
        />
      ),
    },
    productId: {
      key: "productId",
      dataIndex: "productId",
      title: title("productId", fieldTitle.productId),
      width: columnWidths.productId,
      fixed: "left",
      sorter: (a, b) => a.productId.localeCompare(b.productId),
      onHeaderCell: headerCell,
      render: (_, row) => (
        <CopyableTextCell
          text={row.productId}
          label="商品ID"
        />
      ),
    },
    storeOwner: {
      key: "storeOwner",
      title: title("storeOwner", fieldTitle.storeOwner),
      width: columnWidths.storeOwner ?? 172,
      onHeaderCell: headerCell,
      render: (_, row) => (
        <div title={`${row.store} / ${row.owner}`} style={{ lineHeight: "19px", minWidth: 0 }}>
          <div style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {row.store || "-"}
          </div>
          <div style={{ color: "#8C8C8C", fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {row.owner || "-"}
          </div>
        </div>
      ),
    },
    store: {
      key: "store",
      dataIndex: "store",
      title: title("store", fieldTitle.store),
      width: columnWidths.store,
      onHeaderCell: headerCell,
    },
    owner: {
      key: "owner",
      dataIndex: "owner",
      title: title("owner", fieldTitle.owner),
      width: columnWidths.owner,
      onHeaderCell: headerCell,
    },
    sku: {
      key: "sku",
      dataIndex: "sku",
      title: title("sku", fieldTitle.sku),
      width: columnWidths.sku,
      sorter: (a, b) => a.sku.localeCompare(b.sku),
      onHeaderCell: headerCell,
      render: (_, row) => (
        <CopyableTextCell
          text={row.sku}
          label="SKU"
        />
      ),
    },
    productName: {
      key: "productName",
      dataIndex: "productName",
      title: title("productName", fieldTitle.productName),
      width: columnWidths.productName,
      ellipsis: true,
      sorter: (a, b) => a.productName.localeCompare(b.productName),
      onHeaderCell: headerCell,
      render: (_, row) => (
        <CopyableTextCell
          text={row.productName}
          label="商品名称"
          link
          onOpen={() => onOpenDetail(row)}
        />
      ),
    },
    title: {
      key: "title",
      dataIndex: "title",
      title: title("title", fieldTitle.title),
      width: columnWidths.title,
      ellipsis: true,
      onHeaderCell: headerCell,
    },
    productType: {
      key: "productType",
      dataIndex: "productType",
      title: title("productType", fieldTitle.productType),
      width: columnWidths.productType,
      onHeaderCell: headerCell,
    },
    listPrice: {
      key: "listPrice",
      dataIndex: "listPrice",
      title: title("listPrice", fieldTitle.listPrice),
      width: columnWidths.listPrice,
      sorter: (a, b) => (a.listPrice ?? -1) - (b.listPrice ?? -1),
      onHeaderCell: headerCell,
      render: (_, row) => row.listPrice == null ? "—" : `$${row.listPrice.toFixed(2)}`,
    },
    salePrice: {
      key: "salePrice",
      dataIndex: "salePrice",
      title: title("salePrice", fieldTitle.salePrice),
      width: columnWidths.salePrice,
      sorter: (a, b) => (a.salePrice ?? -1) - (b.salePrice ?? -1),
      onHeaderCell: headerCell,
      render: (_, row) => row.salePrice == null ? "—" : `$${row.salePrice.toFixed(2)}`,
    },
    productStatus: {
      key: "productStatus",
      dataIndex: "productStatus",
      title: title("productStatus", fieldTitle.productStatus),
      width: columnWidths.productStatus,
      onHeaderCell: headerCell,
      render: (_, row) => <Tag color={statusColorMap[row.productStatus]}>{row.productStatus}</Tag>,
    },
    lifecycle: {
      key: "lifecycle",
      dataIndex: "lifecycle",
      title: title("lifecycle", fieldTitle.lifecycle),
      width: columnWidths.lifecycle,
      onHeaderCell: headerCell,
      render: (_, row) => {
        const workflowProtected = row.isArchived || ["清货期", "已归档"].includes(row.lifecycle);
        return (
          <span style={{ display: "flex", alignItems: "center", gap: 2, width: "100%" }}>
          {workflowProtected ? (row.lifecycle || "—") : (
            <LifecycleStageSelect row={row} disabled={lifecycleSaving} onSave={onSetLifecycle} />
          )}
          {/* LIFECYCLE_REASONS_LOCAL_V2: explain blank & predicted stages on click. */}
          {row.lifecycleDiagnostic && (
            <Popover
              trigger="click"
              placement="left"
              title="生命周期判定说明"
              content={<LifecycleDiagnosticCard diagnostic={row.lifecycleDiagnostic} />}
            >
              <Button
                type="text"
                size="small"
                aria-label={`查看 ${row.productId} 生命周期计算原因`}
                icon={<InfoCircleOutlined style={{ fontSize: 14, color: "#1677ff" }} />}
                style={{ flexShrink: 0, height: 22, width: 22, padding: 0 }}
              />
            </Popover>
          )}
          </span>
        );
      },
    },
    fulfillmentMethod: {
      key: "fulfillmentMethod",
      dataIndex: "fulfillmentMethod",
      title: title("fulfillmentMethod", fieldTitle.fulfillmentMethod),
      width: columnWidths.fulfillmentMethod,
      onHeaderCell: headerCell,
    },
    gptAnalysis: {
      key: "gptAnalysis",
      title: title("gptAnalysis", fieldTitle.gptAnalysis ?? "GPT分析"),
      width: columnWidths.gptAnalysis,
      align: "center",
      onHeaderCell: headerCell,
      render: (_, row) => (
        <Tooltip title="保存GPT关键词/广告分析链接">
          <Button
            type="text"
            size="small"
            className="listing-management__gpt-analysis-button"
            icon={<RobotOutlined />}
            onClick={() => onOpenGptAnalysis?.(row)}
          />
        </Tooltip>
      ),
    },
    listedAt: {
      key: "listedAt",
      dataIndex: "listedAt",
      title: title("listedAt", fieldTitle.listedAt),
      width: columnWidths.listedAt,
      sorter: (a, b) => a.listedAt.localeCompare(b.listedAt),
      onHeaderCell: headerCell,
    },
    category: {
      key: "category",
      dataIndex: "category",
      title: title("category", fieldTitle.category),
      width: columnWidths.category,
      ellipsis: true,
      onHeaderCell: headerCell,
      render: (_, row) => {
        const fullPath = row.category?.trim() || "";
        const leaf = fullPath
          .split(">")
          .map((part) => part.trim())
          .filter(Boolean)
          .pop() || "—";

        return (
          <Tooltip title={fullPath || "暂无类目"}>
            <span
              style={{
                display: "block",
                width: "100%",
                maxWidth: "100%",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {leaf}
            </span>
          </Tooltip>
        );
      },
    },
    wfsAvailableInventory: {
      key: "wfsAvailableInventory",
      dataIndex: "wfsAvailableInventory",
      title: title("wfsAvailableInventory", fieldTitle.wfsAvailableInventory),
      width: columnWidths.wfsAvailableInventory,
      sorter: (a, b) => a.wfsAvailableInventory - b.wfsAvailableInventory,
      onHeaderCell: headerCell,
    },
    inboundInventory: {
      key: "inboundInventory",
      dataIndex: "inboundInventory",
      title: title("inboundInventory", fieldTitle.inboundInventory),
      width: columnWidths.inboundInventory,
      sorter: (a, b) => a.inboundInventory - b.inboundInventory,
      onHeaderCell: headerCell,
    },
    sales90Days: {
      key: "sales90Days",
      dataIndex: "sales90Days",
      title: title("sales90Days", fieldTitle.sales90Days),
      width: columnWidths.sales90Days,
      sorter: (a, b) => a.sales90Days - b.sales90Days,
      onHeaderCell: headerCell,
    },
    adSpend30Days: {
      key: "adSpend30Days",
      dataIndex: "adSpend30Days",
      title: title("adSpend30Days", fieldTitle.adSpend30Days),
      width: columnWidths.adSpend30Days,
      sorter: (a, b) => a.adSpend30Days - b.adSpend30Days,
      onHeaderCell: headerCell,
      render: (_, row) => `$${row.adSpend30Days.toFixed(2)}`,
    },
    disabledReason: {
      key: "disabledReason",
      dataIndex: "disabledReason",
      title: title("disabledReason", fieldTitle.disabledReason),
      width: columnWidths.disabledReason,
      onHeaderCell: headerCell,
      render: (_, row) => row.disabledReason || "-",
    },
    listingStatus: {
      key: "listingStatus",
      dataIndex: "listingStatus",
      title: title("listingStatus", fieldTitle.listingStatus),
      width: columnWidths.listingStatus,
      onHeaderCell: headerCell,
      render: (_, row) => <Tag color={statusColorMap[row.listingStatus]}>{row.listingStatus}</Tag>,
    },
    buyBoxStatus: {
      key: "buyBoxStatus",
      dataIndex: "buyBoxStatus",
      title: title("buyBoxStatus", fieldTitle.buyBoxStatus),
      width: columnWidths.buyBoxStatus,
      onHeaderCell: headerCell,
      render: (_, row) => <Tag color={statusColorMap[row.buyBoxStatus]}>{row.buyBoxStatus}</Tag>,
    },
    walmartSeller: {
      key: "walmartSeller",
      dataIndex: "walmartSeller",
      title: title("walmartSeller", fieldTitle.walmartSeller),
      width: columnWidths.walmartSeller,
      onHeaderCell: headerCell,
    },
    resold: {
      key: "resold",
      dataIndex: "resold",
      title: title("resold", fieldTitle.resold),
      width: columnWidths.resold,
      onHeaderCell: headerCell,
      render: (_, row) => <Tag color={statusColorMap[row.resold]}>{row.resold}</Tag>,
    },
    checkedAt: {
      key: "checkedAt",
      dataIndex: "checkedAt",
      title: title("checkedAt", fieldTitle.checkedAt),
      width: columnWidths.checkedAt,
      sorter: (a, b) => a.checkedAt.localeCompare(b.checkedAt),
      onHeaderCell: headerCell,
      render: (_, row) => row.checkedAt && row.checkedAt !== "\u672a\u68c0\u6d4b"
        ? row.checkedAt.slice(0, 10) : "\u672a\u68c0\u6d4b",
    },
    rating: {
      key: "rating",
      dataIndex: "rating",
      title: title("rating", fieldTitle.rating),
      width: columnWidths.rating,
      sorter: (a, b) => (a.rating ?? -1) - (b.rating ?? -1),
      onHeaderCell: headerCell,
      render: (_, row) => row.rating ?? "—",
    },
    reviewCount: {
      key: "reviewCount",
      dataIndex: "reviewCount",
      title: title("reviewCount", fieldTitle.reviewCount),
      width: columnWidths.reviewCount,
      sorter: (a, b) => (a.reviewCount ?? -1) - (b.reviewCount ?? -1),
      onHeaderCell: headerCell,
      render: (_, row) => row.reviewCount ?? "—",
    },
    brand: {
      key: "brand",
      dataIndex: "brand",
      title: title("brand", fieldTitle.brand),
      width: columnWidths.brand,
      onHeaderCell: headerCell,
    },
    sellerOfferCount: {
      key: "sellerOfferCount", dataIndex: "sellerOfferCount",
      title: title("sellerOfferCount", fieldTitle.sellerOfferCount),
      width: columnWidths.sellerOfferCount,
      sorter: (a, b) => (a.sellerOfferCount ?? -1) - (b.sellerOfferCount ?? -1),
      onHeaderCell: headerCell,
      render: (_, row) => row.sellerOfferCount ?? "—",
    },
    sellerNames: {
      key: "sellerNames", title: title("sellerNames", fieldTitle.sellerNames),
      width: columnWidths.sellerNames, ellipsis: true, onHeaderCell: headerCell,
      render: (_, row) => row.sellerNames?.length
        ? <Tooltip title={row.sellerNames.join("、")}><span>{row.sellerNames.join("、")}</span></Tooltip>
        : "—",
    },
    hasStrikethrough: {
      key: "hasStrikethrough", title: title("hasStrikethrough", fieldTitle.hasStrikethrough),
      width: columnWidths.hasStrikethrough, onHeaderCell: headerCell,
      render: (_, row) => row.hasStrikethrough == null ? "待检测" : row.hasStrikethrough ? "有" : "无",
    },
    strikethroughSource: {
      key: "strikethroughSource", title: title("strikethroughSource", fieldTitle.strikethroughSource),
      width: columnWidths.strikethroughSource, onHeaderCell: headerCell,
      render: (_, row) => row.strikethroughSource || "—",
    },
    imageCount: {
      key: "imageCount", title: title("imageCount", fieldTitle.imageCount),
      width: columnWidths.imageCount, onHeaderCell: headerCell,
      render: (_, row) => row.imageCount ?? "—",
    },
    imageUrls: {
      key: "imageUrls", title: title("imageUrls", fieldTitle.imageUrls),
      width: columnWidths.imageUrls, onHeaderCell: headerCell,
      render: (_, row) => row.imageUrls?.length ? (
        <Popover title="监控图片URL" content={
          <div style={{ maxWidth: 380, maxHeight: 260, overflowY: "auto" }}>
            {row.imageUrls.map((url, i) => (
              <div key={`${i}-${url}`}><a href={url} target="_blank" rel="noopener noreferrer">图片 {i + 1}</a></div>
            ))}
          </div>
        }>
          <Button type="link" size="small">查看链接 ({row.imageUrls.length})</Button>
        </Popover>
      ) : "—",
    },
    keyFeatures: {
      key: "keyFeatures", title: title("keyFeatures", fieldTitle.keyFeatures),
      width: columnWidths.keyFeatures, onHeaderCell: headerCell,
      render: (_, row) => row.keyFeatures?.length ? (
        <Popover title="最新五点描述" content={
          <ol style={{ maxWidth: 460, maxHeight: 300, overflowY: "auto", paddingLeft: 22 }}>
            {row.keyFeatures.map((value, i) => <li key={i} style={{ marginBottom: 6 }}>{value}</li>)}
          </ol>
        }>
          <Button type="link" size="small">查看 ({row.keyFeatures.length}条)</Button>
        </Popover>
      ) : "—",
    },
    reviewFetchStatus: {
      key: "reviewFetchStatus", title: title("reviewFetchStatus", fieldTitle.reviewFetchStatus),
      width: columnWidths.reviewFetchStatus, onHeaderCell: headerCell,
      render: (_, row) => row.reviewFetchStatus || "—",
    },
    tags: {
      key: "tags",
      dataIndex: "tags",
      title: title("tags", fieldTitle.tags),
      width: columnWidths.tags,
      onHeaderCell: headerCell,
      render: (_, row) => (
        <Space size={4} wrap>
          {row.tags.map((tag) => <Tag key={tag} color="blue">{tag}</Tag>)}
        </Space>
      ),
    },
    productTags: {
      key: "productTags",
      dataIndex: "productTags",
      title: title("productTags", fieldTitle.productTags),
      width: columnWidths.productTags,
      onHeaderCell: headerCell,
      render: (_, row) => {
        const labels = row.productTags ?? [];
        if (!labels.length) {
          const empty: Record<string, string> = {
            pending: "待同步",
            unmatched: "未匹配SKU",
            ambiguous: "SKU匹配冲突",
            no_sku: "SKU缺失",
            matched: "-",
          };
          return <span>{empty[row.productTagMatchStatus ?? "pending"] ?? "-"}</span>;
        }
        return (
          <Space size={4} wrap={false}>
            {labels.slice(0, 2).map((tag, index) => (
              <Tooltip key={`${tag.id ?? tag.label}-${index}`} title={tag.label}>
                <Tag color={tag.color || "default"} style={{ maxWidth: 104, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {tag.label}
                </Tag>
              </Tooltip>
            ))}
            {labels.length > 2 && (
              <Tooltip title={labels.slice(2).map((tag) => tag.label).join("、")}>
                <Tag>+{labels.length - 2}</Tag>
              </Tooltip>
            )}
          </Space>
        );
      },
    },
    gtin: {
      key: "gtin",
      dataIndex: "gtin",
      title: title("gtin", fieldTitle.gtin),
      width: columnWidths.gtin,
      onHeaderCell: headerCell,
    },
    archiveReason: {
      key: "archiveReason",
      dataIndex: "archiveReason",
      title: title("archiveReason", fieldTitle.archiveReason ?? "归档原因"),
      width: columnWidths.archiveReason ?? 180,
      ellipsis: true,
      onHeaderCell: headerCell,
      render: (_, row) => {
        const reason = row.archiveReason?.trim();
        if (!reason) return "-";
        return (
          <Tooltip title={reason}>
            <span>{reason}</span>
          </Tooltip>
        );
      },
    },
    productGrade: {
      key: "productGrade",
      dataIndex: "productGrade",
      title: title("productGrade", fieldTitle.productGrade),
      width: columnWidths.productGrade,
      onHeaderCell: headerCell,
      // SZZSBJ_GRADE_LOCAL_PREVIEW_V1: compact, non-published candidate grade.
      render: (_, row) => {
        const grade = row.productGrade || "待评级";
        const color = grade === "A" ? "green" : grade === "B" ? "blue" :
          grade === "C" ? "orange" : grade === "D" ? "red" : "default";
        const info = row.gradeDiagnostic;
        const percent = (value?: string | null) => {
          if (value == null || value === "") return "暂无数据";
          const number = Number(value);
          return Number.isFinite(number) ? `${number.toFixed(2)}%` : "暂无数据";
        };
        return (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, whiteSpace: "nowrap" }}>
            <Tag color={color} style={{ marginInlineEnd: 0 }}>{grade}</Tag>
            {row.gradePreviewCandidate && <span style={{ fontSize: 10, color: "#777" }}>试算</span>}
            {info && (
              <Popover trigger="click" placement="left" title="产品等级判定说明"
                content={<div style={{ width: 284, fontSize: 12, lineHeight: 1.65 }}>
                  <div style={{ fontWeight: 600, marginBottom: 6 }}>{row.gradePreviewCandidate ? "仅供核对，尚未发布" : grade}</div>
                  <div>{info.reason}</div>
                  {(info.valid7 != null || info.valid14 != null) && (
                    <div style={{ borderTop: "1px solid #eee", paddingTop: 7, marginTop: 8 }}>
                      <div>近7天有效财务：{info.valid7 ?? "—"} 天</div>
                      <div>近14天有效财务：{info.valid14 ?? "—"} 天</div>
                      <div>近7天利润率：{percent(info.margin7)}</div>
                      <div>近14天利润率：{percent(info.margin14)}</div>
                      <div>加权利润率：{percent(info.weightedMargin)}</div>
                    </div>
                  )}
                  <div style={{ color: "#888", borderTop: "1px solid #eee", marginTop: 8, paddingTop: 5 }}>
                    {info.cutoffLa ? `LA数据截止日：${info.cutoffLa}` : "尚未取得截止日"}
                  </div>
                </div>}>
                <Button type="text" size="small" aria-label={`查看 ${row.productId} 等级判定说明`}
                  icon={<InfoCircleOutlined style={{ color: "#1677ff", fontSize: 13 }}/>}
                  style={{ height: 22, width: 22, padding: 0 }}/>
              </Popover>
            )}
          </span>
        );
      },
    },
  };

  const normalizedAppliedColumnKeys = appliedColumnKeys.reduce<string[]>((keys, key) => {
    const normalizedKey = key === "msku" || key === "productId"
      ? "productIdName"
      : key === "sku" || key === "productName"
        ? "skuMsku"
        : key;

    if (!keys.includes(normalizedKey)) keys.push(normalizedKey);
    return keys;
  }, []);

  const columns = normalizedAppliedColumnKeys
    .flatMap((key) => (allColumns[key] ? [allColumns[key]] : []))
    .concat({
      key: "actions",
      title: title("actions", "操作"),
      width: columnWidths.actions,
      fixed: "right",
      onHeaderCell: headerCell,
      render: (_, row) => (
        <Space size={2}>
          <Tooltip title="打开 Listing 详情">
            <Button type="link" onClick={() => onOpenDetail(row)}>详情</Button>
          </Tooltip>
          <Popconfirm
            title={row.isArchived ? "确认恢复该 Listing？" : "确认归档该 Listing？"}
            description={
              row.isArchived
                ? "恢复后该 Listing 会重新回到正常状态。"
                : "归档后按钮会变为恢复，不会删除 Listing 数据。"
            }
            okText={row.isArchived ? "确认恢复" : "确认归档"}
            cancelText="取消"
            onConfirm={() => (
              row.isArchived ? onRestoreListing?.(row) : onArchiveListing?.(row)
            )}
          >
            <Button type="link" danger={!row.isArchived}>
              {row.isArchived ? "恢复" : "归档"}
            </Button>
          </Popconfirm>
        </Space>
      ),
    });

  // Avoid repainting unchanged row contents when selection or other page state
  // changes. Updated records are replaced immutably by the page's mutation handlers.
  const optimizedColumns = columns.map((column) => ({
    ...column,
    shouldCellUpdate: (record: ListingManagementRow, previous: ListingManagementRow) => (
      record !== previous
    ),
  }));
  const scrollX = columns.reduce((sum, column) => sum + Number(column.width ?? 112), 56);

  return (
    <ReportTableShell
      label="Listing 管理表格"
      className={virtual
        ? "listing-management__table-shell listing-management__table-shell--virtual"
        : "listing-management__table-shell"}
    >
      <ProTable<ListingManagementRow>
        rowKey="id"
        search={false}
        options={false}
        dataSource={rows}
        columns={optimizedColumns}
        tableAlertRender={false}
        toolBarRender={false}
        bordered
        size="small"
        scroll={{ x: scrollX, y: virtual ? virtualScrollY : "100%" }}
        virtual={virtual}
        {...(virtual ? { listItemHeight: LISTING_VIRTUAL_ROW_HEIGHT_ESTIMATE } : {})}
        tableLayout="fixed"
        rowSelection={{
          fixed: true,
          selectedRowKeys,
          columnWidth: 48,
          onChange: onSelectionChange,
        }}
        pagination={{
          current: currentPage,
          pageSize,
          total,
          showSizeChanger: true,
          showQuickJumper: true,
          pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS.map(String),
          showTotal: (total) => `共 ${total.toLocaleString()} 条数据`,
          onChange: (page, nextPageSize) => {
            onCurrentPageChange(page);
            if (nextPageSize !== pageSize) onPageSizeChange(nextPageSize);
          },
        }}
        footer={() => (
          <ReportTableSelectionBar
            selectedCount={selectedRowKeys.length}
            actions={[
              {
                key: "edit-lifecycle",
                label: "修改生命周期",
                disabled: selectedRowKeys.length === 0 || lifecycleSaving || !onBatchEditLifecycle,
                onClick: () => onBatchEditLifecycle?.(),
              },
              {
                key: "set-tags",
                label: "设置标签",
                onClick: onBatchSetTags,
              },
              {
                key: "batch-archive",
                label: "批量归档",
                disabled: selectedRowKeys.length === 0 || !onBatchArchive,
                onClick: () => onBatchArchive?.(),
              },
              {
                key: "batch-restore",
                label: "批量恢复",
                disabled: selectedRowKeys.length === 0 || !onBatchRestore,
                onClick: () => onBatchRestore?.(),
              },
              {
                key: "export",
                label: "导出已选",
                disabled: selectedRowKeys.length === 0 || exporting,
                onClick: onBulkExport,
              },
            ]}
          />
        )}
      />
    </ReportTableShell>
  );
}

export default ListingManagementTable;

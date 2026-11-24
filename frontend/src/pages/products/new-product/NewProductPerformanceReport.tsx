/* PR337_APPROVED_CARD_FILTER_V53 */
// PR337_APPROVAL_ITEM_FILTER_20261111
import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Tag, Popover } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import { ImageCell, ProductIdentityCell, SkuMskuIdentityCell } from "@/components/report-table/cells";
import ReportFacetSelect from "@/shared/report-filters";
import type { ReportFilterOption } from "@/shared/report-filters";
import { grade, score, type Config, type Product } from "./nativeData";
import PurchaseReapplyButton from "./PurchaseReapplyButton";
import { prefetchNewProductDetail } from "./newProductBusinessApi";

type Action = "assessment" | "detail" | "market" | "purchase" | "approval" | "resultApproval" | 'calculate' | 'evaluationReview' | 'recheck';
export type PerformanceReportQuery = {
  page:number; pageSize:number; statuses:string[]; owners:string[];
  ratings:string[]; searchField:string; keyword:string;
  phase:string;
};
export type PerformanceRemote = {
  loading:boolean; total:number; error?:string;
  statusOptions:ReportFilterOption[];
  ownerOptions:ReportFilterOption[];
  ratingOptions:ReportFilterOption[];
  onQueryChange:(query:PerformanceReportQuery)=>void;
};
type Props = {
  items: Product[];
  remote?:PerformanceRemote;
  config: Config;
  phase: string;
  onOpen: (kind: Action, id: string) => void;
  onResetPhase: () => void;
  calculatingItemId?: string | null;
  focusItemId?: string | null;
};

const gradeLevels = ["S", "A", "B", "C", "D", "Pass", "pending"];
const searchFields = [
  { value: "sku", label: "SKU" },
  { value: "item", label: "商品ID" },
  { value: "name", label: "品名" },
  { value: "owner", label: "负责人" },
];
const contains = (selected: string[], value: string) =>
  selected.length === 0 || selected.includes(value);


// PR337_AUTO_SCORE_HOVER_V2

// AUTO_SCORE_TOOLTIP_EASY_V1

// PR337_TOOLTIP_RAW_WEIGHTS_V3
function automaticScoreExplanation(row: Product, config: Config) {
  const keys = ["speed", "ad", "profit", "trust"] as const;

  const labels = {
    speed: "出单速度",
    ad: "广告有效性",
    profit: "利润空间",
    trust: "数据可信度",
  };

  const style = {
    width: 390,
    maxWidth: "100%",
    fontSize: 12,
    lineHeight: 1.7,
  };

  if (!row.backend) {
    return <div style={style}>暂无真实评分明细</div>;
  }

  // Closed results are permanently frozen.
  if (
    row.tracking === "打品成功" ||
    row.tracking === "打品失败"
  ) {
    const points = row.backend.automaticWeightedPoints;
    const covered = row.backend.automaticCoveredWeightPct;

    const valid =
      points != null &&
      covered != null &&
      Number.isFinite(Number(points)) &&
      Number.isFinite(Number(covered)) &&
      Number(covered) > 0;

    return (
      <div style={style}>
        <strong>历史自动评分（已冻结）</strong>
        <div style={{color: "#667085", marginTop: 8}}>
          商品已结束打品，不使用当前数据重新计算。
        </div>
        {valid ? (
          <>
            <div style={{marginTop: 8}}>
              历史加权分：
              {Number(points).toFixed(2)}
            </div>
            <div>
              历史覆盖权重：
              {Number(covered)}%
            </div>
            <strong>
              历史得分：
              {(Number(points) * 100 /
                Number(covered)).toFixed(2)} /10
            </strong>
          </>
        ) : (
          <div style={{marginTop: 8}}>
            历史计算明细不可用，不使用当前数据推算。
          </div>
        )}
      </div>
    );
  }

  const dims = row.backend.evaluation.dimensions;

  const entries = keys.flatMap(key => {
    const raw = dims[key];
    const weight = Number(config.weights[key]);

    if (
      raw == null ||
      raw === "" ||
      !Number.isFinite(Number(raw)) ||
      !Number.isFinite(weight) ||
      weight <= 0
    ) {
      return [];
    }

    const value = Number(raw);

    return [{
      key,
      value,
      weight,
      points: value * weight,
    }];
  });

  // Same business formula as the existing automatic-score cell.
  const covered = entries.reduce(
    (sum, x) => sum + x.weight, 0
  );

  const points = entries.reduce(
    (sum, x) => sum + x.points, 0
  );

  const result = covered > 0 ? points / covered : null;

  const weightedTotal = points / 100;

  const rowLine = entries
    .map(x => (x.points / 100).toFixed(2))
    .join(" + ");

  return (
    <div style={style}>
      <div style={{
        fontSize: 15,
        fontWeight: 600,
        marginBottom: 8,
      }}>
        自动评分计算明细
      </div>

      {result !== null ? (
        <>
          <div style={{
            background: "#f5f8ff",
            padding: "10px 12px",
            borderRadius: 6,
            marginBottom: 12,
          }}>
            <span style={{color: "#667085"}}>
              自动评分
            </span>
            <strong style={{
              color: "#1677ff",
              fontSize: 20,
              marginLeft: 8,
            }}>
              {result.toFixed(2)}
            </strong>
            <span style={{color: "#667085"}}>
              {" "}/10 分
            </span>
          </div>

          <div style={{
            fontWeight: 600,
            marginBottom: 8,
          }}>
            第一步：每项得分 × 系统权重
          </div>

          <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 1.25fr 0.8fr",
            gap: 6,
            color: "#667085",
            marginBottom: 6,
          }}>
            <span>评分项目</span>
            <span>计算过程</span>
            <span style={{textAlign: "right"}}>
              加权结果
            </span>
          </div>

          {entries.map(x => (
            <div key={x.key} style={{
              display: "grid",
              gridTemplateColumns: "1fr 1.25fr 0.8fr",
              gap: 6,
              padding: "7px 0",
              borderTop: "1px solid #edf0f3",
              fontVariantNumeric: "tabular-nums",
            }}>
              <span>{labels[x.key]}</span>

              <span>
                {x.value.toFixed(2)}
                {" × "}
                {x.weight}%
              </span>

              <strong style={{textAlign: "right"}}>
                {(x.points / 100).toFixed(2)}
              </strong>
            </div>
          ))}

          <div style={{
            borderTop: "1px solid #e5e7eb",
            marginTop: 10,
            paddingTop: 12,
          }}>
            <div style={{fontWeight: 600}}>
              第二步：将加权结果相加
            </div>

            <div style={{
              display: "flex",
              alignItems: "baseline",
              gap: 8,
              marginTop: 6,
              fontVariantNumeric: "tabular-nums",
              whiteSpace: "nowrap",
              overflowX: "auto",
            }}>
              <span>{rowLine}</span>
              <span>≈ <strong>{weightedTotal.toFixed(2)}</strong></span>
            </div>
          </div>

          <div style={{
            borderTop: "1px solid #e5e7eb",
            marginTop: 12,
            paddingTop: 12,
          }}>
            <div style={{fontWeight: 600}}>
              第三步：换算成 10 分制
            </div>

            <div style={{
              marginTop: 6,
              fontVariantNumeric: "tabular-nums",
            }}>
              {weightedTotal.toFixed(2)}
              {" ÷ "}
              {covered}%
              {" ≈ "}
              <strong style={{
                fontSize: 16,
                color: "#1677ff",
              }}>
                {result.toFixed(2)} 分
              </strong>
            </div>
          </div>

          <div style={{
            marginTop: 12,
            color: "#667085",
            fontSize: 11,
          }}>
            {covered}% 为当前参与评分的系统权重之和。
            不含人工市场竞争评分，缺失维度不参与计算。
            计算使用原始精度；展示保留两位小数，逐项四舍五入可能产生 0.01 的差异。
          </div>
        </>
      ) : (
        <div style={{color: "#98a2b3"}}>
          暂无可参与计算的有效评分数据。
        </div>
      )}
    </div>
  );
}

function NewProductPerformanceReportBody({ items, config, phase, onOpen, onResetPhase, focusItemId, calculatingItemId, remote }: Props) {
  const [statuses, setStatuses] = useState<string[]>([]);
  const [owners, setOwners] = useState<string[]>([]);
  const [ratings, setRatings] = useState<string[]>([]);
  const [searchField, setSearchField] = useState(focusItemId && phase === "approval" ? "item" : "sku");
  const [keyword, setKeyword] = useState(focusItemId && phase === "approval" ? focusItemId : "");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  // NP_DETAIL_CACHE_V4_REFRESH_GUARD: prefetch only after a focused 200ms intent delay.
  const detailIntentTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const detailPrefetchInFlight = useRef(0);
  const cancelDetailIntent = () => {
    if (detailIntentTimer.current !== null) clearTimeout(detailIntentTimer.current);
    detailIntentTimer.current = null;
  };
  const scheduleDetailIntent = (row:Product) => {
    cancelDetailIntent();
    const identity = row.backend?.identity;
    if (!identity?.source_account_ref || !identity.store_id || !identity.item_id) return;
    detailIntentTimer.current = setTimeout(() => {
      detailIntentTimer.current = null;
      if (detailPrefetchInFlight.current >= 2) return;
      detailPrefetchInFlight.current += 1;
      void prefetchNewProductDetail(identity).finally(() => {
        detailPrefetchInFlight.current -= 1;
      });
    }, 200);
  };
  useEffect(() => () => {
    if (detailIntentTimer.current !== null) clearTimeout(detailIntentTimer.current);
  }, []);
  const remoteQueryChanged = remote?.onQueryChange;
  useEffect(() => {
    if (!remoteQueryChanged) return;
    let active = true;
    // Defer parent state updates and ignore obsolete filters after unmount.
    queueMicrotask(() => {
      if (active) remoteQueryChanged({
        page: currentPage, pageSize, statuses, owners, ratings,
        searchField, keyword, phase,
      });
    });
    return () => { active = false; };
  }, [remoteQueryChanged, currentPage, pageSize,
      statuses, owners, ratings, searchField, keyword, phase]);



  // PR337_FLOW_STATUS_MULTI_COUNT_FILTER_20261116
  const statusOptions = useMemo<ReportFilterOption[]>(() => {
    const counts = new Map<string, number>();
    for (const row of items) {
      if (!row.status) continue;
      counts.set(row.status, (counts.get(row.status) ?? 0) + 1);
    }
    return [...counts].map(([value, count]) => ({ value, label: value, count }));
  }, [items]);

  const ownerOptions = useMemo<ReportFilterOption[]>(() =>
    [...new Set(items.map((row) => row.owner))].map((value) => ({
      value, label: value, count: items.filter((row) => row.owner === value).length,
    })), [items]);

  const ratingOptions = useMemo<ReportFilterOption[]>(() =>
    gradeLevels.map((value) => ({
      value,
      label: value === "pending" ? "待评分" : `${value} 级`,
      count: items.filter((row) => (grade(row, config) ?? "pending") === value).length,
    })), [items, config]);


  const filtered = useMemo(() => remote ? items : items.filter((row) => {
    const inPhase = phase === "all" ||
      (phase === "evaluating" && row.status === "测评中") ||
      (phase === "market" && row.status === "待市场评分") ||
      (phase === "pending_confirmation" && row.status === "待测评确认") ||
      (phase === "passed" && row.status === "测评通过") ||
      (phase === "failed" && row.status === "测评未通过");
    const fieldValue = searchField === "item" ? row.item :
      searchField === "name" ? row.name :
      searchField === "owner" ? row.owner : row.sku;
    return inPhase && contains(statuses, row.status) && contains(owners, row.owner) &&
      contains(ratings, grade(row, config) ?? "pending") &&
      (!keyword || (searchField === "item" && keyword === focusItemId
        ? row.item === keyword
        : String(fieldValue).toLowerCase().includes(keyword.toLowerCase())));
  }), [items, config, phase, statuses, owners, ratings, searchField, keyword, focusItemId, remote]);

  const reset = () => {
    setStatuses([]);
    setOwners([]);
    setRatings([]);

    setSearchField("sku");
    setKeyword("");
    setCurrentPage(1);
    onResetPhase();
  };


  type DisplayProduct = Product & {
    imageUrl?: string | null;
    image?: string | null;
    msku?: string | null;
    storeName?: string | null;
    store?: string | null;
  };

  const columns: ProColumns<Product>[] = [
    {
      title: "图片",
      key: "image",
      width: 76,
      align: "center",
      render: (_value, row) => {
        const data = row as DisplayProduct;
        return (
          <ImageCell
            image={data.imageUrl ?? data.image ?? undefined}
            alt={row.name}
            label={`商品图片：${row.name}`}
            thumbnailSize={42}
          />
        );
      },
    },
    {
      title: "商品ID / 品名",
      key: "identity",
      dataIndex: "item",
      width: 245,
      render: (_value, row) => (
        <ProductIdentityCell
          productId={row.item}
          productName={row.name}
        />
      ),
    },
    {
      title: "SKU / MSKU",
      key: "skuMsku",
      width: 165,
      render: (_value, row) => (
        <SkuMskuIdentityCell
          sku={row.sku}
          msku={(row as DisplayProduct).msku || "—"}
        />
      ),
    },
    {
      title: "店铺 / 负责人",
      key: "storeOwner",
      width: 185,
      render: (_value, row) => {
        const data = row as DisplayProduct;
        return (
          <>
            <div className="strong">
              {data.storeName || data.store || "—"}
            </div>
            <div className="cell-sub">
              负责人：{row.owner || "—"}
            </div>
          </>
        );
      },
    },
    {
      title: "测评进度",
      key: "progress",
      width: 165,
      render: (_value, row) => (
        <>
          <div className="strong">
            {row.backend && !row.backend.available.elapsedDays ? '—' : `${row.days} 天`}
            <span className="cell-sub"> · 近7天 {row.backend && !row.backend.available.qty7 ? '—' : row.qty7} {row.backend ? '件' : '单'}</span>
          </div>
          <div className="cell-sub">首次可售：{row.backend ? row.backend.firstWfsDate || '—' : row.arrival || '—'}</div>
          <div className="cell-sub">首单日期：{row.backend?.firstOrderDate || '—'}</div>
        </>
      ),
    },
    {
      title: "自动评分",
      key: "automatic",
      width: 195,
      render: (_value, row) => (
        <>
          <Popover trigger="hover" placement="topLeft" content={automaticScoreExplanation(row, config)}>
<div className="score-main">
            {row.backend ? (
              (() => {
                // Closed products retain their saved automatic score.
                if (row.tracking === '打品成功' || row.tracking === '打品失败') {
                  const points = row.backend?.automaticWeightedPoints;
                  const coverage = row.backend?.automaticCoveredWeightPct;
                  return points != null && coverage != null && coverage > 0
                    ? (points * 100 / coverage).toFixed(2)
                    : '—';
                }

                // Use exactly the dimensions displayed in this column.
                const dims = row.backend?.evaluation.dimensions;
                const keys = (['speed', 'ad', 'profit', 'trust'] as const)
                  .filter(key => {
                    const raw = dims?.[key];
                    return raw !== null && raw !== undefined && raw !== ''
                      && Number.isFinite(Number(raw))
                      && Number.isFinite(config.weights[key])
                      && config.weights[key] > 0;
                  });

                const covered = keys.reduce(
                  (sum, key) => sum + config.weights[key], 0
                );

                if (covered <= 0) return '—';

                const points = keys.reduce(
                  (sum, key) =>
                    sum + Number(dims?.[key]) * config.weights[key], 0
                );

                return (points / covered).toFixed(2);
              })()
              ) : (
              (row.scores.speed*30+row.scores.ad*20+row.scores.profit*25+row.scores.trust*10)/85
            ).toFixed(2)}
            <span className="muted"> /10{row.backend ? `` : ''}</span>
          </div>
</Popover>
          <div className="cell-sub">
            出单 {(row.backend && !row.backend.available.speed) ? '—' : Number(row.scores.speed).toFixed(2)} · 广告 {(row.backend && !row.backend.available.ad) ? '—' : Number(row.scores.ad).toFixed(2)}
          </div>
          <div className="cell-sub">
            利润 {(row.backend && !row.backend.available.profit) ? '—' : Number(row.scores.profit).toFixed(2)} · 可信 {(row.backend && !row.backend.available.trust) ? '—' : Number(row.scores.trust).toFixed(2)}
          </div>
        </>
      ),
    },
    {
      title: "市场竞争",
      key: "market",
      width: 165,
      render: (_value, row) => (
        <div>
          {(row.status === "测评中" || (row.backend && !row.backend.firstWfsDate && !row.launch)) &&
            row.tracking !== "打品成功" && row.tracking !== "打品失败" ? (
            <span className="muted">—</span>
          ) : row.market === null ? (
            <Tag color="orange">{row.status === "待计算" ? "待计算" : "待人工评分"}</Tag>
          ) : (
            <>
              <div className="score-main">{row.market} /10</div>
              <div className="cell-sub">已填写依据</div>
            </>
          )}
        </div>
      ),
    },
    {
      title: "总分 / 评级",
      key: "grade",
      width: 155,
      render: (_value, row) => {
        const total = row.status === "测评中" ? null : score(row, config);
        const rating = row.status === "测评中" ? null : grade(row, config);

        const tone =
          rating === "S" ? "grade-s" :
          rating === "A" ? "grade-a" :
          rating === "B" ? "grade-b" :
          rating === "C" ? "grade-c" : "grade-d";

        return total === null ? (
          <span className="muted">{row.status === "测评中" ? "—" : "待评分"}</span>
        ) : (
          <>
            <div className="score-main">{total.toFixed(2)}</div>
            <div className="cell-sub">
              <span className={`grade ${tone}`}>{rating}</span> 级
            </div>
          </>
        );
      },
    },
    {
      title: "流程状态",
      key: "status",
      dataIndex: "status",
      width: 160,
      render: (_value, row) => {
        const color =
          row.status === "待市场评分" ? "orange" :
          row.status === "测评中" ? "blue" :
          row.status === "测评通过" ? "green" :
          row.status === "测评未通过" ? "red" : "default";
        if (row.backend?.purchaseStatus === "rejected") return <span>
          <Tag color={color}>{row.status}</Tag>
          <Popover trigger="click" content={<div style={{maxWidth:360,whiteSpace:"pre-wrap"}}>
            <strong>采购申请已驳回</strong>
            <div>驳回原因：{row.backend.purchaseReviewReason || "历史记录未提供驳回原因"}</div>
            {row.backend.purchaseReviewedBy && <div>审批人：{row.backend.purchaseReviewedBy}</div>}
            {row.backend.purchaseReviewedAt && <div>审批时间：{row.backend.purchaseReviewedAt.slice(0,19).replace("T"," ")}</div>}
          </div>}>
            <Button type="link" size="small">采购已驳回 · 查看原因</Button>
          </Popover>
        </span>;
        return <Tag color={color}>{row.status}</Tag>;
      },
    },
    {
      title: "操作", key: "actions", width: 184, fixed: "right",
      render: (_value, row) => {
        const state = row.status;
        if (state === "待到货") return <span className="muted">—</span>;
        if (row.backend?.purchaseStatus === "submitted" && row.backend.purchaseId) return <Button size="small" onMouseEnter={() => scheduleDetailIntent(row)} onMouseLeave={cancelDetailIntent} onFocus={() => scheduleDetailIntent(row)} onBlur={cancelDetailIntent} onClick={() => onOpen("detail",row.id)} style={{ minWidth: 58, borderRadius: 8, borderColor: "#d0d5dd", color: "#344054", fontWeight: 500 }}>详情</Button>;
        if (row.backend?.purchaseStatus === "rejected") return <span style={{display:"inline-flex",gap:12,alignItems:"center",whiteSpace:"nowrap"}}>
          <Button size="small" onClick={() => onOpen("detail",row.id)}>详情</Button>
          <PurchaseReapplyButton product={row}/>
        </span>;
        if (state === "测评中") return <span style={{ display: "inline-flex", alignItems: "center", gap: 12, whiteSpace: "nowrap" }}>
          <Button size="small" onMouseEnter={() => scheduleDetailIntent(row)} onMouseLeave={cancelDetailIntent} onFocus={() => scheduleDetailIntent(row)} onBlur={cancelDetailIntent} onClick={() => onOpen("detail",row.id)} style={{ minWidth: 58, borderRadius: 8, borderColor: "#d0d5dd", color: "#344054", fontWeight: 500 }}>详情</Button>
          <Button size="small" type="primary" disabled={calculatingItemId === row.id}
            onClick={() => onOpen("calculate",row.id)}>
            {calculatingItemId === row.id ? "计算中" : "立即计算"}
          </Button>
        </span>;
        if (state === "待市场评分") return <span style={{ display: "inline-flex", alignItems: "center", gap: 12, whiteSpace: "nowrap" }}>
          <Button size="small" disabled={calculatingItemId === row.id}
            onClick={() => onOpen("calculate",row.id)}>
            {calculatingItemId === row.id ? "计算中" : "立即计算"}
          </Button>
          <Button size="small" type="primary"
            onClick={() => onOpen("market",row.id)}>去评分</Button>
        </span>;
        if (state === "待等级确认") return <Button size="small"
          onClick={() => onOpen("detail", row.id)}>详情</Button>;
        if (state === "待测评确认") return <span style={{ display: "inline-flex", alignItems: "center", gap: 12, whiteSpace: "nowrap" }}>
          <Button size="small" onClick={() => onOpen("detail",row.id)}>详情</Button>
          <Button size="small" type="primary" onClick={() => onOpen("assessment",row.id)}>确认测评</Button>
        </span>;
        if (state === "测评未通过") return <span style={{ display: "inline-flex", alignItems: "center", gap: 12, whiteSpace: "nowrap" }}>
          <Button size="small" onMouseEnter={() => scheduleDetailIntent(row)} onMouseLeave={cancelDetailIntent} onFocus={() => scheduleDetailIntent(row)} onBlur={cancelDetailIntent} onClick={() => onOpen("detail",row.id)} style={{ minWidth: 58, borderRadius: 8, borderColor: "#d0d5dd", color: "#344054", fontWeight: 500 }}>详情</Button>
          {row.evaluationRecheckRequired && row.evaluationReviewStatus === "approved" ?
            <Button size="small" type="primary" disabled={calculatingItemId === row.id}
              onClick={() => onOpen("recheck",row.id)}>重新核算</Button> :
            row.evaluationReviewStatus === "submitted" || row.evaluationReviewStatus === "info_required" ?
            <Button size="small" disabled>复核审核中</Button> :
            row.evaluationManualException ? <Button size="small" disabled>人工特批</Button> :
            <Button size="small" type="primary"
              onClick={() => onOpen("evaluationReview",row.id)}>
              {row.evaluationReviewStatus === "rejected" ? "重新申请" : "申请复核"}</Button>}
        </span>;
        if (state === "测评通过") return <span style={{ display: "inline-flex", alignItems: "center", gap: 12, whiteSpace: "nowrap" }}>
<Button size="small"
          onMouseEnter={() => scheduleDetailIntent(row)} onMouseLeave={cancelDetailIntent} onFocus={() => scheduleDetailIntent(row)} onBlur={cancelDetailIntent} onClick={() => onOpen("detail",row.id)} style={{ minWidth: 58, borderRadius: 8, borderColor: "#d0d5dd", color: "#344054", fontWeight: 500 }}>详情</Button>
{row.backend && ["S","A","B","C"].includes(row.backend.evaluation.grade ?? "") && row.backend.evaluation.total !== null && (row.backend.suggestedQty ?? 0) > 0 && <Button size="small" type="primary" onClick={() => onOpen("purchase",row.id)}>申请采购</Button>}
</span>;
        return <span className="muted">—</span>;
      },
    },
  ];

  return <section className={phase==="approved"?"np-performance-report np-approved-report":"np-performance-report"} aria-label="新品表现明细">
    <div className="np-performance-toolbar" role="search" aria-label="新品表现筛选">
      <ReportFacetSelect mode="multiple" ariaLabel="流程状态" placeholder="全部状态"
        unit="项" value={statuses} options={remote?.statusOptions ?? statusOptions}
        onChange={(value) => { setStatuses(Array.isArray(value) ? value : []); setCurrentPage(1); }} />
      <ReportFacetSelect mode="multiple" ariaLabel="负责人" placeholder="全部负责人"
        unit="人" value={owners} options={remote?.ownerOptions ?? ownerOptions}
        onChange={(value) => { setOwners(Array.isArray(value) ? value : []); setCurrentPage(1); }} />
      <ReportFacetSelect mode="multiple" ariaLabel="评级" placeholder="全部评级"
        unit="项" value={ratings} options={remote?.ratingOptions ?? ratingOptions}
        onChange={(value) => { setRatings(Array.isArray(value) ? value : []); setCurrentPage(1); }} />
      <CommittedSearch className="np-performance-search"
        typeAriaLabel="搜索类型" typeOptions={searchFields}
        typeValue={searchField} inputAriaLabel="搜索新品" inputPlaceholder="搜索 SKU、Item ID、品名"
        inputValue={keyword}
        onCommit={({ searchField: nextField, keyword: nextKeyword }) => {
          setSearchField(nextField);
          setKeyword(nextKeyword);
          setCurrentPage(1);
        }} />
      <ResetButton onClick={reset} />
    </div>
    {phase==="approved"&&<div className="np-performance-heading np-approved-heading"><strong>已通过商品</strong><span>仅展示已审批通过的商品 · 可查看评分与采购建议</span></div>}
    <ReportTableShell label={phase==="approved"?"已通过商品表格":"新品测品结果表格"} className="np-performance-table-shell">
      <ProTable<Product>
        key={phase}
        className="np-performance-protable"
        rowKey="id"
        columns={columns}
        dataSource={filtered}
        loading={remote?.loading ?? false}
        locale={remote?.error ? {emptyText: "商品读取失败，请点击刷新重试"} : undefined}
        search={false}
        options={false}
        toolBarRender={false}
        scroll={{ x: 1480, y: "100%" }}
        pagination={{
          current: currentPage,
          pageSize,
          total: remote ? remote.total : filtered.length,
          showSizeChanger: true,
          pageSizeOptions: ["20", "50"],
          showTotal: (total, range) => `显示 ${range[0]}–${range[1]} 条，共 ${total} 条`,
          onChange: (page, size) => {
            setCurrentPage(page);
            setPageSize(size);
          },
        }}
      />
    </ReportTableShell>
  </section>;
}

export default function NewProductPerformanceReport(props: Props) {
  return <NewProductPerformanceReportBody key={`${props.phase}:${props.focusItemId ?? ""}`} {...props} />;
}

// NP_PURCHASE_REAPPLY_SELF_CONTAINED_V5

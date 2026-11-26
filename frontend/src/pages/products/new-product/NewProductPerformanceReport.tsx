/* PR337_APPROVED_CARD_FILTER_V53 */
// PR337_APPROVAL_ITEM_FILTER_20261111
import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Tag, Popover, Tooltip } from "antd";
import dayjs from "dayjs";
import ReportDateRangePicker from "@/shared/date/ReportDateRangePicker";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import { ImageCell, ProductIdentityCell, SkuMskuIdentityCell } from "@/components/report-table/cells";
import ReportFacetSelect from "@/shared/report-filters";
import type { ReportFilterOption } from "@/shared/report-filters";
import { grade, score, type Config, type Product } from "./newProductModel";
import PurchaseReapplyButton from "./PurchaseReapplyButton";
import { passedPurchaseView } from "./newProductPassedPurchaseView";
import { performanceFlowStatus, performanceStageStatuses } from "./newProductPerformanceStages";
import { prefetchNewProductDetail, type FirstWfsDateRange } from "./newProductBusinessApi";

type Action = "assessment" | "detail" | "market" | "purchase" | "approval" | "resultApproval" | 'calculate' | 'evaluationReview' | 'recheck';
export type PerformanceReportQuery = {
  page:number; pageSize:number; statuses:string[]; owners:string[];
  ratings:string[]; searchField:string; keyword:string;
  phase:string;
};
export type PerformanceRemote = {
  loading:boolean; total:number; error?:string;
  statusOptions:ReportFilterOption[];
  initialQuery?:PerformanceReportQuery;
  ownerOptions:ReportFilterOption[];
  ratingOptions:ReportFilterOption[];
  firstWfsDateRange?:FirstWfsDateRange;
  onFirstWfsDateRangeChange:(range:FirstWfsDateRange|undefined)=>void;
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
const assessmentDateFormatter = new Intl.DateTimeFormat("sv-SE", {timeZone:"Asia/Taipei",year:"numeric",month:"2-digit",day:"2-digit"});
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
  const initial = remote?.initialQuery;
  const [statuses, setStatuses] = useState<string[]>(() => initial?.phase === phase ? initial.statuses.filter(s=>performanceStageStatuses(phase).includes(s)) : []);
  const [owners, setOwners] = useState<string[]>(() => initial?.owners ?? []);
  const [ratings, setRatings] = useState<string[]>(() => initial?.ratings ?? []);
  const [searchField, setSearchField] = useState(focusItemId && phase === "approval" ? "item" : initial?.searchField ?? "sku");
  const [keyword, setKeyword] = useState(focusItemId && phase === "approval" ? focusItemId : initial?.keyword ?? "");
  const [currentPage, setCurrentPage] = useState(1);
  const [localFirstWfsRange,setLocalFirstWfsRange]=useState<FirstWfsDateRange>();
  const firstWfsDateRange=remote?remote.firstWfsDateRange:localFirstWfsRange;
  const changeFirstWfsRange=(range:FirstWfsDateRange|undefined)=>{
    if(remote) remote.onFirstWfsDateRangeChange(range);
    else setLocalFirstWfsRange(range);
    setCurrentPage(1);
  };
  const [pageSize, setPageSize] = useState(initial?.pageSize ?? 50);
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
      const status = performanceFlowStatus(row);
      if (!status) continue;
      counts.set(status, (counts.get(status) ?? 0) + 1);
    }
    return performanceStageStatuses(phase).map(value => ({ value, label: value, count: counts.get(value) ?? 0 }));
  }, [items, phase]);
  const visibleStatusOptions = (remote?.statusOptions ?? statusOptions).filter(option=>performanceStageStatuses(phase).includes(option.value));

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
    const currentStatus = performanceFlowStatus(row);
    const inPhase = phase === "all" || performanceStageStatuses(phase).includes(currentStatus);
    const fieldValue = searchField === "item" ? row.item :
      searchField === "name" ? row.name :
      searchField === "owner" ? row.owner : row.sku;
    const firstWfs=row.backend?.firstWfsDate;
    const inDateRange=!firstWfsDateRange || (!!firstWfs && firstWfsDateRange[0]<=firstWfs && firstWfs<=firstWfsDateRange[1]);
    return inDateRange && inPhase && contains(statuses, currentStatus) && contains(owners, row.owner) &&
      contains(ratings, grade(row, config) ?? "pending") &&
      (!keyword || (searchField === "item" && keyword === focusItemId
        ? row.item === keyword
        : String(fieldValue).toLowerCase().includes(keyword.toLowerCase())));
  }), [items, config, phase, statuses, owners, ratings, searchField, keyword, focusItemId, remote, firstWfsDateRange]);

  const reset = () => {
    setStatuses([]);
    setOwners([]);
    setRatings([]);
    changeFirstWfsRange(undefined);

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
              {phase !== "passed" && phase !== "failed" && "负责人："}{row.owner || "—"}
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
            {phase === "failed" && row.backend?.evaluationDecision?.decision === "failed" && (() => {
              const value = row.backend.evaluationDecision.confirmed_at;
              const d = new Date(value);
              return value && !Number.isNaN(d.getTime()) ? <div className="cell-sub" title="测评未通过确认日期">{assessmentDateFormatter.format(d)}</div> : null;
            })()}
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
        const current = performanceFlowStatus(row);
        const color = current.includes("驳回") || current === "测评未通过" ? "red" :
          current === "采购已批准" ? "green" :
          current.includes("审批中") || current === "待重新核算" || performanceStageStatuses("pending").includes(current) ? "orange" :
          current === "测评中" ? "blue" : "default";
        if ((phase === "passed" && current === "采购审批中") || (phase === "failed" && current === "复核审批中")) return <Tag color="blue">{current}</Tag>;
        if (current === "采购已驳回" && phase !== "passed") return <span>
          <Tag color={color}>{current}</Tag>
          <Popover trigger="click" content={<div style={{maxWidth:360,whiteSpace:"pre-wrap"}}>
            <strong>采购申请已驳回</strong>
            <div>驳回原因：{row.backend?.purchaseReviewReason || "历史记录未提供驳回原因"}</div>
            {row.backend?.purchaseReviewedBy && <div>审批人：{row.backend?.purchaseReviewedBy}</div>}
            {row.backend?.purchaseReviewedAt && <div>审批时间：{row.backend?.purchaseReviewedAt.slice(0,19).replace("T"," ")}</div>}
          </div>}>
            <Button type="link" size="small">查看原因</Button>
          </Popover>
        </span>;
        return <Tag color={color}>{current}</Tag>;
      },
    },
    {
      title: "操作", key: "actions", width: 184, fixed: "right",
      render: (_value, row) => {
        const state = row.status;
        if ((row.evaluationStatus ?? state) === "测评未通过") {
          const info = row.backend?.failedAssessmentInfo;
          const pending = row.evaluationReviewStatus === "submitted" || row.evaluationReviewStatus === "info_required";
          const actionStyle = {minWidth:78,borderRadius:8,borderColor:"#91caff",color:"#1677ff",fontWeight:500};
          return <span style={{display:"inline-flex",alignItems:"center",gap:8,whiteSpace:"nowrap"}}>
            <Button size="small" onMouseEnter={() => scheduleDetailIntent(row)} onMouseLeave={cancelDetailIntent} onFocus={() => scheduleDetailIntent(row)} onBlur={cancelDetailIntent} onClick={() => onOpen("detail",row.id)}>详情</Button>
            {row.evaluationRecheckRequired && row.evaluationReviewStatus === "approved" ?
              <Button size="small" style={actionStyle} disabled={calculatingItemId===row.id} onClick={()=>onOpen("recheck",row.id)}>{calculatingItemId===row.id?"核算中":"重新核算"}</Button> :
              pending ? <Popover trigger="click" content={<div style={{maxWidth:340,whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>
                <strong>复核申请</strong><div>{info?.review_request_reason || "历史记录未提供申请说明"}</div>
                {info?.review_decision_reason && <div>审批意见：{info.review_decision_reason}</div>}
                <div style={{color:"#667085"}}>审批中，请到审批工作台处理。</div>
              </div>}><Button size="small" style={actionStyle}>查看复核</Button></Popover> :
              row.evaluationManualException && !info?.manual_pass_allowed ? <Button size="small" disabled>人工特批</Button> :
              <Button size="small" style={actionStyle} onClick={()=>onOpen("evaluationReview",row.id)}>{row.evaluationReviewStatus==="rejected"?"重新申请":"申请复核"}</Button>}
          </span>;
        }
        if (phase === "passed" && row.backend?.purchaseStatus === "approved") return <Button size="small"
          onMouseEnter={() => scheduleDetailIntent(row)} onMouseLeave={cancelDetailIntent}
          onFocus={() => scheduleDetailIntent(row)} onBlur={cancelDetailIntent}
          onClick={() => onOpen("detail", row.id)}>详情</Button>;
        if (performanceFlowStatus(row) === "待到货") return <Button size="small"
          onClick={() => onOpen("detail", row.id)}>详情</Button>;
        if (row.backend?.purchaseStatus === "submitted" && row.backend.purchaseId) return <Button size="small" onMouseEnter={() => scheduleDetailIntent(row)} onMouseLeave={cancelDetailIntent} onFocus={() => scheduleDetailIntent(row)} onBlur={cancelDetailIntent} onClick={() => onOpen("detail",row.id)} style={{ minWidth: 58, borderRadius: 8, borderColor: "#d0d5dd", color: "#344054", fontWeight: 500 }}>{phase === "passed" ? "查看审批" : "详情"}</Button>;
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
          <Button size="small" style={{ minWidth: 78, borderRadius: 8, borderColor: "#91caff", color: "#1677ff", fontWeight: 500 }}
            onClick={() => onOpen("market",row.id)}>市场评分</Button>
        </span>;
        if (state === "待等级确认") return <Button size="small" style={{ minWidth: 78, borderRadius: 8, borderColor: "#91caff", color: "#1677ff", fontWeight: 500 }}
          onClick={() => onOpen("detail", row.id)}>确认等级</Button>;
        if (state === "待测评确认") return <span style={{ display: "inline-flex", alignItems: "center", gap: 12, whiteSpace: "nowrap" }}>
          <Button size="small" onClick={() => onOpen("detail",row.id)}>详情</Button>
          <Button size="small" style={{ minWidth: 78, borderRadius: 8, borderColor: "#91caff", color: "#1677ff", fontWeight: 500 }} onClick={() => onOpen("assessment",row.id)}>确认测评</Button>
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

  const purchaseColumns: ProColumns<Product>[] = [
    {
      title: "采购数量", key: "passedPurchaseQty", width: 116,
      render: (_value, row) => {
        const v = passedPurchaseView(row);
        const changed = v.delta !== null && v.delta !== 0;
        const qtyLine = (label: "建议" | "申请" | "批准", qty: number | null) => {
          const approved = label === "批准";
          const highlight = approved && changed;
          return (
            <div style={{display:"grid",gridTemplateColumns:"30px minmax(0,1fr) 12px",alignItems:"baseline",columnGap:4,lineHeight:approved?"24px":"20px"}}>
              <span style={{color:label==="建议"?"#98a2b3":"#475467",fontSize:13,fontWeight:approved?600:400}}>{label}</span>
              <span style={{textAlign:"right",color:qty===null?"#98a2b3":highlight?"#d97706":label==="建议"?"#98a2b3":"#1f2937",fontSize:approved&&qty!==null?18:14,fontWeight:approved&&qty!==null?700:label==="申请"?600:400,fontVariantNumeric:"tabular-nums",whiteSpace:"nowrap"}}>{qty ?? "—"}</span>
              <span style={{color:"#d97706",fontSize:14,fontWeight:700}}>{highlight && <span aria-label={v.delta! > 0 ? "批准数量增加" : "批准数量减少"}>{v.delta! > 0 ? "↑" : "↓"}</span>}</span>
            </div>
          );
        };
        return <div style={{maxWidth:100}}>{qtyLine("建议",v.suggested)}{qtyLine("申请",v.requested)}{qtyLine("批准",v.approvedQty)}</div>;
      },
    },
    {
      title: "采购店铺", key: "passedPurchaseStore", width: 175,
      render: (_value,row) => {
        const change = passedPurchaseView(row).storeChange;
        if (!change) return <span className="muted">—</span>;
        return <Tooltip title={change.to}>
          <strong style={{display:"block",color:"#d97706",fontSize:14,fontWeight:700,lineHeight:"20px",whiteSpace:"normal",overflowWrap:"anywhere"}}>{change.to}</strong>
        </Tooltip>;
      },
    },
    {
      title: "审批信息", key: "passedPurchaseReason", width: 220,
      render: (_value,row) => {
        const v = passedPurchaseView(row);
        if (!v.reason) return <span className="muted">—</span>;
        return <Tooltip title={<span style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{v.reason}</span>}>
          <div style={{color:v.rejected?"#cf1322":"#475467",lineHeight:"20px",display:"-webkit-box",WebkitLineClamp:2,WebkitBoxOrient:"vertical",overflow:"hidden",overflowWrap:"anywhere"}}>{v.reason}</div>
        </Tooltip>;
      },
    },
  ];
  const failedColumns: ProColumns<Product>[] = [
    {
      title:"未通过原因",key:"failedAssessmentReason",width:235,
      render:(_value,row)=>{
        const verdict=row.backend?.evaluationDecision;
        const info=row.backend?.failedAssessmentInfo;
        if(verdict?.decision!=="failed") return <span className="muted">—</span>;
        const label=info?.reason_kind==="risk_limit"?"风险限制":info?.reason_kind==="grade_limit"?"评级限制":"人工判定";
        const reason=verdict.reason?.trim();
        return <div>
          <strong style={{fontSize:13,color:info?.reason_kind==="risk_limit"||info?.reason_kind==="grade_limit"?"#cf1322":"#344054"}}>{label}</strong>
          {reason ? <Tooltip title={<span style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{reason}</span>}>
            <div style={{color:"#475467",lineHeight:"20px",display:"-webkit-box",WebkitLineClamp:2,WebkitBoxOrient:"vertical",overflow:"hidden",overflowWrap:"anywhere"}}>{reason}</div>
          </Tooltip> : <div className="cell-sub">—</div>}
        </div>;
      },
    },
    {
      title:"复核信息",key:"failedReviewInfo",width:235,
      render:(_value,row)=>{
        const info=row.backend?.failedAssessmentInfo;
        const concluded=row.evaluationReviewStatus==="approved"||row.evaluationReviewStatus==="rejected";
        const reason=(concluded?info?.review_decision_reason:info?.review_request_reason)?.trim();
        if(!reason) return <span className="muted">—</span>;
        const full=concluded && info?.review_request_reason ? `申请说明：${info.review_request_reason}\n审批意见：${reason}` : reason;
        return <Tooltip title={<span style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{full}</span>}>
          <div style={{color:row.evaluationReviewStatus==="rejected"?"#cf1322":"#475467",lineHeight:"20px",display:"-webkit-box",WebkitLineClamp:2,WebkitBoxOrient:"vertical",overflow:"hidden",overflowWrap:"anywhere"}}>{reason}</div>
        </Tooltip>;
      },
    },
  ];
  const visibleColumns = phase === "passed" || phase === "failed" ? columns.flatMap(column =>
    ["progress", "automatic", "market"].includes(String(column.key)) ? [] :
      column.key === "status" ? [...(phase === "passed" ? purchaseColumns : failedColumns), column] : [column]
  ) : columns;

  return <section className={phase==="approved"?"np-performance-report np-approved-report":"np-performance-report"} aria-label="新品表现明细">
    <div className="np-performance-toolbar" role="search" aria-label="新品表现筛选">
      <ReportFacetSelect mode="multiple" ariaLabel="流程状态" placeholder="全部状态"
        unit="项" value={statuses} options={visibleStatusOptions}
        onChange={(value) => { setStatuses(Array.isArray(value) ? value : []); setCurrentPage(1); }} />
      <ReportFacetSelect mode="multiple" ariaLabel="负责人" placeholder="全部负责人"
        unit="人" value={owners} options={remote?.ownerOptions ?? ownerOptions}
        onChange={(value) => { setOwners(Array.isArray(value) ? value : []); setCurrentPage(1); }} />
      <ReportFacetSelect mode="multiple" ariaLabel="评级" placeholder="全部评级"
        unit="项" value={ratings} options={remote?.ratingOptions ?? ratingOptions}
        onChange={(value) => { setRatings(Array.isArray(value) ? value : []); setCurrentPage(1); }} />
      <ReportDateRangePicker
        aria-label="WFS首次可售日期范围"
        allowClear
        placeholder={["首次可售开始日期","首次可售结束日期"]}
        value={firstWfsDateRange?[dayjs(firstWfsDateRange[0]),dayjs(firstWfsDateRange[1])]:null}
        style={{width:290,flex:"0 0 auto"}}
        onChange={dates=>changeFirstWfsRange(dates?.[0] && dates[1]
          ? [dates[0].format("YYYY-MM-DD"),dates[1].format("YYYY-MM-DD")] : undefined)}
      />
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
        columns={visibleColumns}
        dataSource={filtered}
        loading={remote?.loading ?? false}
        locale={remote?.error ? {emptyText: "商品读取失败，请点击刷新重试"} : undefined}
        search={false}
        options={false}
        toolBarRender={false}
        scroll={{ x: phase === "passed" ? 1696 : phase === "failed" ? 1655 : 1480, y: "100%" }}
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

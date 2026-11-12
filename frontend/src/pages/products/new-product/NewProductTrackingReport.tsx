import "./trackingSharedCommittedSearch.css";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import { TrackingSystemRecommendation, TrackingTriggeredRules } from "./TrackingRuleSignals";
import { EditOutlined, EyeOutlined } from "@ant-design/icons";
// PR337_TRACKING_EDITABLE_PENDING_V4
// PR337_TRACKING_OUTCOME_LOCK_V3
import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Segmented, Tag, Tooltip } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import { ImageCell, ProductIdentityCell, SkuMskuIdentityCell } from "@/components/report-table/cells";
import ReportFacetSelect from "@/shared/report-filters";
import type { ReportFilterOption } from "@/shared/report-filters";
import { suggestion, type Config, type Product, type Grade } from "./nativeData";
import { getTrackingPool } from "./trackingBoardMetrics";
import { matchesTrackingBoardDrill, trackingOwner, trackingGrade, type TrackingDrillFilter } from "./trackingBoardDrilldown";
import "./newProductTrackingReport.css";

// PR337_TRACKING_COMPONENTS_V1 — page-specific composition of shared components.
type Props = {
  products: Product[];
  config: Config;
  onReview: (id: string, sourceRow?: Product) => void;
  drill?: TrackingDrillFilter | null;
  onClearDrill?:()=>void;
};

type DisplayProduct = Product & {
  imageUrl?: string | null;
  image?: string | null;
  msku?: string | null;
  storeName?: string | null;
  store?: string | null;
};

type StatKey = "all" | "success" | "observe" | "optimize" | "failure" | "undecided";

const outcomeOf = (
  row: Product
): Exclude<StatKey, "all"> => {
  switch (row.tracking) {
    case "打品成功": return "success";
    case "继续观察": return "observe";
    case "需要优化": return "optimize";
    case "打品失败": return "failure";
    default: return "undecided";
  }
};
const gradeChoices: Array<Grade|"待评分"> = ["S", "A", "B", "C", "D", "Pass", "待评分"];


const optionsWithCounts = (
  choices: string[],
  rows: Product[],
  test: (row: Product, choice: string) => boolean,
): ReportFilterOption[] => choices.map((value) => ({
  value,
  label: value,
  count: rows.filter((row) => test(row, value)).length,
}));

function NewProductTrackingReport({ products, config, onReview, drill=null, onClearDrill }: Props) {
  const [period, setPeriod] = useState<30 | 60 | 180>(30);
  const [grades, setGrades] = useState<string[]>(() => drill?.kind==='grade'&&drill.value?[drill.value]:[]);
  const [owners,setOwners] = useState<string[]>(() => drill?.kind==='owner'&&drill.value?[drill.value]:[]);
  const [search,setSearch] = useState(() => drill?.kind==='item'?drill.value??'':'');
  const [stat, setStat] = useState<StatKey>("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [scrollY, setScrollY] = useState(360);
  const viewport = useRef<HTMLDivElement>(null);

  const rows=useMemo(()=>getTrackingPool(products),[products]);
  const displayRows=rows;
  const scopedRows=useMemo(()=>displayRows.filter(row=>matchesTrackingBoardDrill(row,drill)),[displayRows,drill]);
  const ownerOptions=useMemo(()=>optionsWithCounts(
    [...new Set(scopedRows.map(trackingOwner))].sort((a,b)=>a.localeCompare(b,'zh-CN')),
    scopedRows,(row,value)=>trackingOwner(row)===value
  ),[scopedRows]);
  const gradeOptions = useMemo(() => optionsWithCounts(
    gradeChoices, scopedRows, (row, value) => trackingGrade(row, config) === value,
  ).map((item) => ({ ...item, label: item.value==="待评分"?"待评分":`${item.label} 级` })), [scopedRows, config]);


  const visibleCohort = useMemo(() =>
    scopedRows.filter(row =>
      (grades.length===0 || grades.includes(trackingGrade(row,config))) &&
      (owners.length===0 || owners.includes(trackingOwner(row))) &&
      (!search.trim() || `${row.item} ${row.sku} ${row.name}`.toLowerCase().includes(search.trim().toLowerCase()))
    ), [scopedRows, grades, owners, search, config]);

  const filtered = useMemo(() =>
    visibleCohort.filter(row =>
      stat === "all" || outcomeOf(row) === stat
    ), [visibleCohort, stat]);

  useEffect(() => {
    const node = viewport.current;
    if (!node) return;
    const update = () => {
      // Reserve the table header/pagination within the actual flex viewport.
      const available = Math.max(140, node.clientHeight - 88);
      setScrollY((previous) => Math.abs(available - previous) > 1 ? available : previous);
    };
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(node);
    window.addEventListener("resize", update);
    update();
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);
  const changeStat = (key: StatKey) => {
    setStat((current) => current === key && key !== "all" ? "all" : key);
    setPage(1);
  };


  // PR337_SIX_RESULT_CARDS_V1
  const countByOutcome = (key: StatKey): number =>
    key === "all"
      ? visibleCohort.length
      : visibleCohort.filter(
          row => outcomeOf(row) === key
        ).length;

  const cards = [
    {
      key: "all" as const,
      title: "全部商品",
      subtitle: "当前跟踪商品",
      value: countByOutcome("all"),
      tone: "normal" as const,
      icon: <span>▣</span>,
    },
    {
      key: "success" as const,
      title: "打品成功",
      subtitle: "最终结果已锁定",
      value: countByOutcome("success"),
      tone: "success" as const,
      icon: <span>✓</span>,
    },
    {
      key: "observe" as const,
      title: "继续观察",
      subtitle: "尚未形成最终结论",
      value: countByOutcome("observe"),
      tone: "normal" as const,
      icon: <span>◷</span>,
    },
    {
      key: "optimize" as const,
      title: "需要优化",
      subtitle: "可继续人工判定",
      value: countByOutcome("optimize"),
      tone: "warning" as const,
      icon: <span>↗</span>,
    },
    {
      key: "failure" as const,
      title: "打品失败",
      subtitle: "最终结果已锁定",
      value: countByOutcome("failure"),
      tone: "danger" as const,
      icon: <span>×</span>,
    },
    {
      key: "undecided" as const,
      title: "未判定",
      subtitle: "包含等待开售",
      value: countByOutcome("undecided"),
      tone: "normal" as const,
      icon: <span>•</span>,
    },
  ];

  const columns: ProColumns<Product>[] = [
    { title: "图片", key: "image", width: 64, align: "center",
      render: (_unused, row) => {
        const item = row as DisplayProduct;
        return <ImageCell image={item.imageUrl ?? item.image ?? undefined}
          alt={row.name} label={`图片：${row.name}`} thumbnailSize={42} />;
      },
    },
    { title: "商品ID / 品名", key: "identity", dataIndex: "item", width: 207,
      render: (_unused, row) => <ProductIdentityCell productId={row.item} productName={row.name} />,
    },
    { title: "SKU / MSKU", key: "skuMsku", width: 148,
      render: (_unused, row) => <SkuMskuIdentityCell sku={row.sku}
        msku={(row as DisplayProduct).msku || "—"} />,
    },
    { title: "店铺 / 负责人", key: "storeOwner", width: 157,
      render: (_unused, row) => {
        const item = row as DisplayProduct;
        return <div><div className="np-tracking-cell-main">{item.storeName || item.store || "—"}</div>
          <div className="np-tracking-cell-sub">负责人：{trackingOwner(row)}</div></div>;
      },
    },
    { title: "初始评级", key: "initialGrade", width: 88,
      render: (_unused, row) => {
        // PR337's Mock does not persist an immutable initial-grade snapshot.
        const value = trackingGrade(row,config);
        const textClass = value === "S" ? "s" : value === "A" ? "a" :
          value === "B" ? "b" : value === "C" ? "c" : "d";
        return <Tooltip title="有初始评级快照时优先使用；缺失时以当前评分作模拟参考">
          <span className={`np-tracking-grade np-tracking-grade--${textClass}`}>{value==="待评分"?"待评分":`${value} 级`}</span>
        </Tooltip>;
      },
    },
    { title: "建议量 / 批准量", key: "qty", width: 151,
      render: (_unused, row) => <div>
        <div className="np-tracking-cell-main">{row.backend && row.backend.suggestedQty===null ? "—" : suggestion(row, config)} / {row.actualQty > 0 ? row.actualQty : "—"} 件</div>
        <div className="np-tracking-cell-sub">建议 / 已有采购数量</div>
      </div>,
    },
    { title: "追踪起点", key: "arrival", dataIndex: "arrival", width: 142,
      render: (_unused, row) => <div>
        <div className="np-tracking-cell-main">{row.arrival || "等待到货 / 可售"}</div>
        {row.arrival && <div className="np-tracking-cell-sub">{row.backend?'WFS首次可售日期':'到货日期（示例）'}</div>}
      </div>,
    },
    {
      title: `${period}天销量`,
      key: "periodSales",
      width: 102,
      render: (_unused, row) => <div>
        <div className="np-tracking-cell-main">
          {row.backend ? (period===30 && row.backend.available.sales30 ? row.sold30 : '—') :
            (period === 30 ? row.sold30 : period === 60 ? row.sold60 : "—")}
        </div>
        {period === 180 && (
          <div className="np-tracking-cell-sub">
            暂无180天数据
          </div>
        )}
      </div>,
    },
    { title: "利润率", key: "margin", width: 80,
      render: (_unused, row) => <span>{row.backend ? (row.backend.available.margin ? `${row.margin}%` : '—') : `${row.margin60 || row.margin}%`}</span>,
    },
    { title: "ACOS", key: "acos", width: 79,
      render: (_unused, row) => <span>{row.backend ? (row.backend.available.acos ? `${row.acos}%` : '—') : `${row.acos60 || row.acos}%`}</span>,
    },
    { title: "当前库存", key: "inventory", dataIndex: "inventory", width: 105,
      render: (_unused, row) => <strong>{row.backend && !row.backend.available.inventory ? '—' : `${row.inventory} 件`}</strong>,
    },
    // PR337_RULE_SIGNAL_POPOVER_V1 — system advice never writes human decisions.
    { title: "系统建议", key: "trackingSystemRecommendation", width: 140,
      render: (_unused, row) => <TrackingSystemRecommendation product={row} />,
    },
    { title: "触发规则", key: "trackingTriggeredRules", width: 174,
      render: (_unused, row) => <TrackingTriggeredRules product={row} />,
    },
    { title: "打品结果", key: "outcome", dataIndex: "tracking", width: 138,
      render: (_unused, row) => {
        const undecided = row.tracking === "等待开售" || row.tracking === "未判定";
        if (undecided) {
          const launched = Boolean(row.launch?.trim() && row.arrival?.trim());
          return <div><Tag>未判定</Tag>
            <div className="np-tracking-cell-sub">
              {launched ? "已开售 · 待人工判定" : "跟踪阶段：等待开售"}
            </div>
          </div>;
        }
        const color = row.tracking === "打品成功" ? "green" :
          row.tracking === "打品失败" ? "red" :
          row.tracking === "需要优化" ? "orange" :
          row.tracking === "继续观察" ? "blue" : "default";
        return <Tag color={color}>{row.tracking || "未判定"}</Tag>;
      },
    },
    { title: "操作", key: "actions", width: 116, fixed: "right",
      render: (_unused, row) => {
        const terminal = row.tracking === "打品成功" || row.tracking === "打品失败";
        const undecided = row.tracking === "等待开售" || row.tracking === "未判定";
        // Only a Mock proxy. Real implementation requires explicit Listing sellable flag.
        const launched = Boolean(row.launch?.trim() && row.arrival?.trim());
        const label = terminal ? "查看结果" :
          undecided && !launched ? "查看阶段" :
          "人工判定";
        const isView = terminal || (undecided && !launched);

        return (
          <Button
            type="link"
            size="small"
            icon={isView ? <EyeOutlined /> : <EditOutlined />}
            onClick={() => onReview(row.id, row)}
            style={{
              paddingInline: 2,
              minWidth: 0,
              height: 30,
              fontSize: 13,
              fontWeight: 500,
              color: isView ? "#667085" : "#1677ff",
              background: "transparent",
              border: "none",
              boxShadow: "none",
            }}
          >
            {label}
          </Button>
        );
      },
    },
  ];

  return <div className="np-tracking-report">
    <ManagementStatCards ariaLabel="打品跟踪统计" className="np-tracking-summary"
      cards={cards} activeKey={stat} onCardClick={changeStat} />
    <div className="np-tracking-toolbar" aria-label="打品筛选">
      <ReportFacetSelect mode="multiple" ariaLabel="负责人" placeholder="全部负责人"
        value={owners} options={ownerOptions} unit="人"
        onChange={(value)=>{setOwners(Array.isArray(value)?value:[]);setPage(1);}} />

      <ReportFacetSelect mode="multiple" ariaLabel="初始评级" placeholder="全部初始评级"
        value={grades} options={gradeOptions} unit="级"
        onChange={(value) => { setGrades(Array.isArray(value) ? value : []); setPage(1); }} />
      <CommittedSearch
        className="np-tracking-committed-search"
        typeAriaLabel="搜索类型"
        typeOptions={[{ value: "all", label: "全部" }]}
        typeValue="all"
        inputAriaLabel={"搜索商品ID、SKU或品名"}
        inputPlaceholder={"搜索商品ID / SKU / 品名"}
        inputValue={search}
        onCommit={({ keyword }) => { setSearch(keyword); setPage(1); }}
      />
      <Button size="small" onClick={()=>{setOwners([]);setGrades([]);setSearch('');setStat('all');setPage(1);onClearDrill?.();}}>重置</Button>
      <div className="np-tracking-period">
        <span className="np-tracking-period-label">数据周期：</span>
        <Segmented
          className="np-tracking-period-control"
          options={[
            { label: "30天", value: 30 },
            { label: "60天", value: 60 },
            { label: "180天", value: 180 },
          ]}
          value={period}
          onChange={(value) => {
            setPeriod(value as 30 | 60 | 180);
            setPage(1);
          }}
        />
      </div>
    </div>
    {drill&&<div className="np-tracking-board-scope" role="status">
      <Tag closable onClose={()=>{setOwners([]);setGrades([]);setSearch('');onClearDrill?.();}}>
        来自打品看板：{drill.label}（{drill.from} 至 {drill.to}）
      </Tag>
    </div>}
    <div ref={viewport} className="np-tracking-shell-viewport">
      <ReportTableShell label="打品跟踪明细表" className="np-tracking-report-shell">
        <ProTable<Product>
          className="np-tracking-protable"
          rowKey="id"
          columns={columns}
          dataSource={filtered}
          search={false}
          options={false}
          toolBarRender={false}
          scroll={{ x: 1531, y: scrollY }}
          pagination={{
            current: page,
            pageSize,
            total: filtered.length,
            showSizeChanger: true,
            pageSizeOptions: ["20", "50"],
            showTotal: (total, range) => `显示 ${range[0]}–${range[1]} 条，共 ${total} 条`,
            onChange: (nextPage, nextSize) => {
              setPage(nextPage);
              setPageSize(nextSize);
            },
          }}
        />
      </ReportTableShell>
    </div>
  </div>;
}

export default NewProductTrackingReport;

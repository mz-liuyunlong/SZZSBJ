/* PR337_APPROVED_CARD_FILTER_V53 */
// PR337_APPROVAL_ITEM_FILTER_20261111
import { useMemo, useState } from "react";
import { Button, Tag, Popover } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import { ImageCell, ProductIdentityCell, SkuMskuIdentityCell } from "@/components/report-table/cells";
import ReportFacetSelect from "@/shared/report-filters";
import type { ReportFilterOption } from "@/shared/report-filters";
import { grade, score, type Config, type Product } from "./nativeData";

type Action = "detail" | "market" | "purchase" | "approval";
type Props = {
  items: Product[];
  config: Config;
  phase: string;
  onOpen: (kind: Action, id: string) => void;
  onResetPhase: () => void;
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

function NewProductPerformanceReportBody({ items, config, phase, onOpen, onResetPhase, focusItemId }: Props) {
  const [owners, setOwners] = useState<string[]>([]);
  const [ratings, setRatings] = useState<string[]>([]);
  const [searchField, setSearchField] = useState(focusItemId && phase === "approval" ? "item" : "sku");
  const [keyword, setKeyword] = useState(focusItemId && phase === "approval" ? focusItemId : "");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);



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


  const filtered = useMemo(() => items.filter((row) => {
    const inPhase = phase === "all" ||
      (phase === "market" && row.status === "待市场评分") ||
      (phase === "purchase" && row.status === "待采购确认") ||
      (phase === "approval" && row.status === "审核中") ||
      (phase === "approved" && ["已批准","已通过","审批通过"].includes(row.status));
    const fieldValue = searchField === "item" ? row.item :
      searchField === "name" ? row.name :
      searchField === "owner" ? row.owner : row.sku;
    return inPhase && contains(owners, row.owner) &&
      contains(ratings, grade(row, config) ?? "pending") &&
      (!keyword || (searchField === "item" && keyword === focusItemId
        ? row.item === keyword
        : String(fieldValue).toLowerCase().includes(keyword.toLowerCase())));
  }), [items, config, phase, owners, ratings, searchField, keyword, focusItemId]);

  const reset = () => {
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
            出单 {row.backend && !row.backend.available.speed ? '—' : Number(row.scores.speed).toFixed(2)} · 广告 {row.backend && !row.backend.available.ad ? '—' : Number(row.scores.ad).toFixed(2)}
          </div>
          <div className="cell-sub">
            利润 {row.backend && !row.backend.available.profit ? '—' : Number(row.scores.profit).toFixed(2)} · 可信 {row.backend && !row.backend.available.trust ? '—' : Number(row.scores.trust).toFixed(2)}
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
          {row.market === null ? (
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
        const total = score(row, config);
        const rating = grade(row, config);

        const tone =
          rating === "S" ? "grade-s" :
          rating === "A" ? "grade-a" :
          rating === "B" ? "grade-b" :
          rating === "C" ? "grade-c" : "grade-d";

        return total === null ? (
          <span className="muted">待评分</span>
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
          row.status === "待采购确认" ? "blue" :
          row.status === "审核中" ? "purple" :
          row.status === "已批准" ? "green" :
          row.status.includes("停止") ||
          row.status.includes("失败") ||
          row.status.includes("驳回") ? "red" :
          "default";

        return (
          <>
            <Tag color={color}>{row.status}</Tag>
            <div className="cell-sub">{row.risk || "—"}</div>
          </>
        );
      },
    },
    {
      title: "操作", key: "actions", width: 142, fixed: "right",
      render: (_value, row) => {
        if (["已批准","已通过","审批通过"].includes(row.status)) {
          return <Button size="small" onClick={() => onOpen("detail", row.id)}>详情</Button>;
        }
        const state = row.status;
        const action: Action = state === "待市场评分" ? "market" :
          state === "待采购确认" ? "purchase" :
          state === "审核中" ? "approval" : "detail";
        const label = state === "待市场评分" ? "去评分" :
          state === "待采购确认" ? "确认采购" :
          state === "审核中" ? "查看申请" : "详情";
        const primary = state === "待市场评分" || state === "待采购确认";
        return <Button type={primary ? "primary" : "default"} size="small"
          onClick={() => onOpen(action, row.id)}>{label}</Button>;
      },
    },
  ];

  return <section className={phase==="approved"?"np-performance-report np-approved-report":"np-performance-report"} aria-label="新品表现明细">
    <div className="np-performance-toolbar" role="search" aria-label="新品表现筛选">
      <ReportFacetSelect mode="multiple" ariaLabel="负责人" placeholder="全部负责人"
        unit="人" value={owners} options={ownerOptions}
        onChange={(value) => { setOwners(Array.isArray(value) ? value : []); setCurrentPage(1); }} />
      <ReportFacetSelect mode="multiple" ariaLabel="评级" placeholder="全部评级"
        unit="项" value={ratings} options={ratingOptions}
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
        search={false}
        options={false}
        toolBarRender={false}
        scroll={{ x: 1480, y: "100%" }}
        pagination={{
          current: currentPage,
          pageSize,
          total: filtered.length,
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

/* PR337_APPROVED_CARD_FILTER_V53 */
// PR337_APPROVAL_ITEM_FILTER_20261111
import { useMemo, useState } from "react";
import { Button, Tag } from "antd";
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

function NewProductPerformanceReportBody({ items, config, phase, onOpen, onResetPhase, focusItemId }: Props) {
  const [owners, setOwners] = useState<string[]>([]);
  const [ratings, setRatings] = useState<string[]>([]);
  const [searchField, setSearchField] = useState(focusItemId && phase === "approval" ? "item" : "sku");
  const [keyword, setKeyword] = useState(focusItemId && phase === "approval" ? focusItemId : "");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);



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
          <div className="strong">{row.days} 天</div>
          <div className="cell-sub">
            首单已记录 · 近7天 {row.qty7} 单
          </div>
        </>
      ),
    },
    {
      title: "自动评分",
      key: "automatic",
      width: 195,
      render: (_value, row) => (
        <>
          <div className="score-main">
            {(
              (
                row.scores.speed * 30 +
                row.scores.ad * 20 +
                row.scores.profit * 25 +
                row.scores.trust * 10
              ) / 85
            ).toFixed(1)}
            <span className="muted"> /10</span>
          </div>
          <div className="cell-sub">
            出单 {row.scores.speed} · 广告 {row.scores.ad}
          </div>
          <div className="cell-sub">
            利润 {row.scores.profit} · 可信 {row.scores.trust}
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
            <Tag color="orange">待人工评分</Tag>
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

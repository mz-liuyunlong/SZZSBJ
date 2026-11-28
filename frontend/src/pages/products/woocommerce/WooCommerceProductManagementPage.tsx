import { useEffect, useState } from "react";
import { Alert, Button, Card, Empty, Typography } from "antd";
import { ExportOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import { ImageCell, CopyableTextCell } from "@/components/report-table/cells";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import { REPORT_TABLE_DEFAULT_PAGE_SIZE, REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import ReportFacetSelect, { type ReportFilterOption, type ReportFacetSelectValue } from "@/shared/report-filters";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import type { WooProductRow } from "./wooCommerceProductTypes";
import { fetchWooProducts, type WooCatalog } from "./wooCommerceProductsApi";
import { BackendRequestError } from "@/api/backendApi";
import WooCommercePublishRulesPreview from "./WooCommercePublishRulesPreview";
import "./WooCommerceProductManagementPage.css";

const { Text } = Typography;
const statuses = [{ value: "all", label: "全部商品" }, { value: "publish", label: "已发布" }, { value: "draft", label: "草稿" }, { value: "pending", label: "待审核" }, { value: "private", label: "私密" }, { value: "other", label: "其他状态" }];
const stockOptions = [{ value: "instock", label: "有货" }, { value: "outofstock", label: "缺货" }, { value: "onbackorder", label: "缺货可订购" }];
const statusLabel = (status: string) => status === "missing" ? "独立站未返回" : statuses.find(item => item.value === status)?.label ?? status;
const stockLabel = (status: string) => stockOptions.find(item => item.value === status)?.label ?? status;
const money = (value: string) => value === "" ? "—" : Number.isFinite(Number(value)) ? Number(value).toFixed(2) : value;


export default function WooCommerceProductManagementPage({ page }: { page: NavigationPage }) {
  const [catalog, setCatalog] = useState<WooCatalog>({items: [], total: 0, summary: {}, stores: [], brands: []});
  const [rulesPreviewOpen, setRulesPreviewOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [keyword, setKeyword] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [searchType, setSearchType] = useState("all");
  const [appliedSearchType, setAppliedSearchType] = useState("all");
  const [store, setStore] = useState<string[]>([]);
  const [brand, setBrand] = useState<string[]>([]);
  const [stock, setStock] = useState<string[]>([]);
  const [description, setDescription] = useState<string[]>([]);
  const [status, setStatus] = useState("all");
  const [current, setCurrent] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [sortKey, setSortKey] = useState("listedAt");
  const [sortOrder, setSortOrder] = useState<"ascend" | "descend">("descend");
  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams({page:String(current), page_size:String(pageSize), keyword, search_type:appliedSearchType, status, sort_key:sortKey, sort_order:sortOrder});
    for (const [key, values] of [["store",store],["brand",brand],["stock",stock],["description",description]] as const) values.forEach(v => query.append(key,v));
    setLoading(true); setError("");
    void fetchWooProducts(query, controller.signal).then(data => {
      if (!controller.signal.aborted) { setCatalog(data); if (current > Math.max(1,Math.ceil(data.total/pageSize))) setCurrent(1); }
    }).catch(err => { if (!controller.signal.aborted) { setCatalog({items:[],total:0,summary:{},stores:[],brands:[]}); setError(err instanceof BackendRequestError ? String(err.code || "BACKEND_ERROR") : "NETWORK_ERROR"); } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [reload, keyword, appliedSearchType, store, brand, stock, description, status, current, pageSize, sortKey, sortOrder]);
  const {items:rows, stores, brands} = catalog;
  const applyFacet = (setter: (values: string[]) => void, value: ReportFacetSelectValue) => {
    setter(Array.isArray(value) ? value : typeof value === "string" ? [value] : []);
    setCurrent(1);
  };
  const facet = (label: string, value: string[], options: ReportFilterOption[], setter: (values: string[]) => void) => (
    <ReportFacetSelect mode="multiple" ariaLabel={label} placeholder={label} value={value} options={options} onChange={next => applyFacet(setter, next)} />
  );
  const columns: ProColumns<WooProductRow>[] = [
    { title: "图片", key: "image", width: 76, fixed: "left", render: (_, row) => row.imageUrl ? <ImageCell src={row.imageUrl} alt={row.name} label="商品主图" thumbnailSize={48} /> : <span className="woo-products__image-pending" aria-label="主图链接尚未采集">—</span> },
    { title: "名称", key: "name", width: 300, sorter: true, sortOrder: sortKey === "name" ? sortOrder : null, render: (_, row) => <div className="woo-products__name"><div className="woo-products__title" title={row.name}>{row.name}</div><div className="woo-products__subline"><span>ID: {row.id}</span>{row.url && <a href={row.url} target="_blank" rel="noopener noreferrer" aria-label="打开独立站商品"><ExportOutlined /> 独立站</a>}</div></div> },
    { title: "店铺名称", key: "store", width: 116, sorter: true, sortOrder: sortKey === "store" ? sortOrder : null, render: (_, row) => <span title={row.store}>{row.store}</span> },
    { title: "Walmart店铺 / 商品ID", key: "sources", width: 190, render: (_, row) => row.sources.length ? <div>{row.sources.map(source => <div key={JSON.stringify([source.account,source.storeId,source.itemId])}><div>{source.storeName}</div>{source.url ? <a href={source.url} target="_blank" rel="noopener noreferrer">{source.itemId}</a> : <span>{source.itemId}</span>}</div>)}</div> : <Text type="secondary">未关联</Text> },
    { title: "图片数量", key: "images", width: 112, align: "center", sorter: true, sortOrder: sortKey === "images" ? sortOrder : null, render: (_, row) => <Text type={row.images === 0 ? "danger" : undefined}>{row.images} 张</Text> },
    { title: "描述", key: "description", width: 152, render: (_, row) => <div>{row.points.length ? <details className="woo-products__description"><summary>五点 {row.points.length}/5</summary><ol>{row.points.map((point, index) => <li key={index}>{point}</li>)}</ol></details> : <Text type="secondary">五点未确认</Text>}<div className="woo-products__muted">{row.descriptionLength > 0 ? "长描述有内容" : "长描述为空"}</div></div> },
    { title: "SKU", dataIndex: "sku", key: "sku", width: 120, sorter: true, sortOrder: sortKey === "sku" ? sortOrder : null, render: (_, row) => row.sku ? <CopyableTextCell text={row.sku} label="SKU" /> : <Text type="danger">未填写</Text> },
    { title: "库存", key: "stock", width: 122, sorter: true, sortOrder: sortKey === "stock" ? sortOrder : null, render: (_, row) => <div><Text type={row.stockStatus === "outofstock" ? "danger" : undefined}>{stockLabel(row.stockStatus)}</Text><div className="woo-products__muted">{row.stockQuantity === null ? "数量未知" : `${row.stockQuantity} 件`}</div></div> },
    { title: "价格", key: "price", width: 112, align: "right", sorter: true, sortOrder: sortKey === "price" ? sortOrder : null, render: (_, row) => <div><Text strong>{row.price && row.currency ? `${row.currency} ${money(row.price)}` : "—"}</Text>{row.regularPrice && row.regularPrice !== row.price && <div><Text delete type="secondary">{money(row.regularPrice)}</Text></div>}</div> },
    { title: "品牌", key: "brand", width: 125, sorter: true, sortOrder: sortKey === "brand" ? sortOrder : null, render: (_, row) => row.brands.length ? row.brands.join("、") : <Text type="danger">未填写</Text> },
    { title: "上架时间", key: "listedAt", width: 150, sorter: true, sortOrder: sortKey === "listedAt" ? sortOrder : null, render: (_, row) => <div>{row.listedAt ? row.listedAt.slice(0, 10) : <Text type="secondary">未确认</Text>}<div className="woo-products__muted">创建 {row.createdAt ? row.createdAt.slice(0, 10) : "—"}</div></div> },
    { title: "发布状态", key: "status", width: 126, sorter: true, sortOrder: sortKey === "status" ? sortOrder : null, render: (_, row) => <span title={`最近同步: ${row.lastSyncedAt}`} className={`woo-products__status ${row.status === "publish" ? "woo-products__status--published" : ""}`}><i aria-hidden="true" />{statusLabel(row.status)}</span> },
  ];
  const reset = () => { setKeyword(""); setSearchDraft(""); setSearchType("all"); setAppliedSearchType("all"); setStore([]); setBrand([]); setStock([]); setDescription([]); setStatus("all"); setSortKey("listedAt"); setSortOrder("descend"); setCurrent(1); };
  const summary = statuses.map(item => ({ ...item, count: catalog.summary[item.value] ?? 0 }));
  return <PageShell page={page}>
    <Card size="small" className="woo-products">
      <div className="woo-products__heading"><h1>WooCommerce产品管理</h1><div><Button loading={loading} onClick={() => setReload(n => n + 1)}>刷新数据</Button> <Button onClick={() => setRulesPreviewOpen(true)}>自动刊登规则</Button></div></div>
      {error && <Alert type="error" showIcon message={`商品读取失败：${error}`} />}
      <div className="woo-products__summary" aria-label="发布状态筛选">
        {summary.map(item => <Button key={item.value} type="text" className={`woo-products__metric ${status === item.value ? "woo-products__metric--active" : ""}`} aria-pressed={status === item.value} onClick={() => { setStatus(item.value); setCurrent(1); }}><span>{item.label}</span><strong>{item.count}</strong></Button>)}
      </div>
      <div className="woo-products__toolbar" role="search" aria-label="WooCommerce 商品筛选">
        {facet("店铺名称", store, stores, setStore)}
        {facet("品牌", brand, [...brands.map(value => ({ value, label: value })), { value: "missing", label: "品牌未填写" }], setBrand)}
        {facet("库存", stock, stockOptions, setStock)}
        {facet("描述", description, [{ value: "complete", label: "五点完整" }, { value: "unconfirmed", label: "五点未完整确认" }], setDescription)}
        <ConnectedSearch typeAriaLabel="搜索类型" typeOptions={[{value:"all",label:"全部"},{value:"name",label:"名称"},{value:"sku",label:"SKU"},{value:"id",label:"商品ID"}]} typeValue={searchType} inputAriaLabel="搜索商品" inputPlaceholder="名称 / SKU / 商品ID" inputValue={searchDraft} onTypeChange={setSearchType} onInputChange={setSearchDraft} onSearch={() => { setKeyword(searchDraft.trim()); setAppliedSearchType(searchType); setCurrent(1); }} />
        <ResetButton onClick={reset} />
      </div>
      <ReportTableShell label="WooCommerce 商品列表" className="woo-products__table-shell">
        <ProTable<WooProductRow> rowKey={row => `${row.storeId}:${row.id}`} loading={loading} columns={columns} dataSource={rows} onChange={(_, __, sorter) => { const value = Array.isArray(sorter) ? sorter[0] : sorter; const key = String(value?.columnKey ?? "listedAt"); const order = value?.order === "ascend" ? "ascend" : "descend"; if (key !== sortKey || order !== sortOrder) { setSortKey(key); setSortOrder(order); setCurrent(1); } }} search={false} options={false} tableAlertRender={false} toolBarRender={false} bordered size="small" tableLayout="fixed" scroll={{ x: 1690, y: "100%" }} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={error ? "商品读取失败" : "没有符合条件的商品"} /> }} pagination={{ current, pageSize, total: catalog.total, showSizeChanger: true, showQuickJumper: true, pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS.map(String), showTotal: total => `共 ${total.toLocaleString()} 条数据`, onChange: (next, size) => { setCurrent(size === pageSize ? next : 1); setPageSize(size); } }} />
      </ReportTableShell>
    </Card>
    <WooCommercePublishRulesPreview open={rulesPreviewOpen} onClose={() => setRulesPreviewOpen(false)} />
  </PageShell>;
}

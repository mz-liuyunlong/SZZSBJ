/**
 * 资金流水 · 备货资金（第 7 组，本地预览只读）。对应 Demo「⑦ 资金流水 · 备货资金」（v51 CashStock + TabCapital）。
 * 布局照 PMC 采购看板：标题 → 筛选卡（店铺 / 视图）→ 统计卡（点卡片切视图）→ 一张表占满；口径说明在右上角「？帮助」。
 */
import { Segmented, Tag, Typography } from "antd";
import { type ProColumns, ProTable } from "@ant-design/pro-components";
import { useMemo, useState } from "react";
import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResetButton from "@/components/report-table/ResetButton";
import FinanceBoardFrame, { FinMoney } from "@/pages/finance/FinanceBoardFrame";
import ReportFacetSelect from "@/shared/report-filters";
import EmptyState from "@/shared/states/EmptyState";
import HelpButton from "./HelpButton";
import { useStock, type StockDomestic, type StockFile, type StockTransit, type StockWfs } from "./data";
import "./cash-flow.css";

type View = "inv" | "wfs" | "age" | "transit" | "domestic";
interface InvRow { m: string; qty: number; goods: number; head: number; other: number; total: number }
interface AgeRow { label: string; qty: number; amount: number; share: number }

const VIEW_LABEL: Record<View, string> = { inv: "发货投入（按月）", wfs: "WFS 在仓", age: "WFS 库龄", transit: "在途货件", domestic: "国内仓" };
const AGE = ["0–90 天", "91–180 天", "181–270 天", "271–365 天", "365 天以上"];
const n0 = (value: number | null | undefined) => (value == null || !Number.isFinite(value) ? "—" : Math.round(value).toLocaleString("en-US"));
const yuan = (value: number) => `¥${n0(value)}`;
const sum = <T,>(rows: T[], pick: (row: T) => number) => rows.reduce((acc, row) => acc + (pick(row) || 0), 0);
const unitCell = (value: number) => (value ? <FinMoney value={value} /> : <Typography.Text type="secondary">无</Typography.Text>);
const icon = (text: string) => <span className="management-stat-card__mark">{text}</span>;
const scrollX = <T,>(columns: ProColumns<T>[]) => columns.reduce((acc, col) => acc + (typeof col.width === "number" ? col.width : 120), 0);

function StockTable<T extends object>({ label, rowKey, rows, columns, emptyText }: {
  label: string; rowKey: (row: T) => string; rows: T[]; columns: ProColumns<T>[]; emptyText: string;
}) {
  return (
    <ReportTableShell label={label}>
      <ProTable<T>
        rowKey={rowKey}
        search={false}
        options={false}
        toolBarRender={false}
        tableAlertRender={false}
        bordered
        size="small"
        dataSource={rows}
        columns={columns}
        scroll={{ x: scrollX(columns), y: "100%" }}
        locale={{ emptyText: <EmptyState title="没有记录" description={emptyText} compact /> }}
        pagination={{ defaultPageSize: 50, showSizeChanger: true, showQuickJumper: true, showTotal: (count) => `共 ${count.toLocaleString()} 条` }}
      />
    </ReportTableShell>
  );
}

/** 备货资金页的「？帮助」：口径说明都放这里。 */
export function CashStockHelp({ data }: { data?: StockFile }) {
  return (
    <HelpButton
      title="备货资金"
      sections={[
        { title: "这页看什么", body: "备货资金 = 每月为备货花了多少（发货投入，流量）+ 现在压在货上多少（库存货值，存量）。PMC 板块看件数与时间，这里只看钱。数据是 PMC 每日快照，财务这边只读。" },
        { title: "发货投入", body: "按领星发货单的发货月汇总：货物（采购）+ 头程 + 税 / 辅料，单位人民币。" },
        { title: "库存货值", body: <>GTIN 单件入库成本 × 时点库存（PMC 快照 {data?.meta.daily ?? "—"}）。WFS 用「在库」件数计金额；找不到入库成本的 GTIN 单价显示「无」、按 0 计。在途 = 已建货件、Walmart 还没收货的件数。国内仓分「挂店铺的批次」和「未分店（公司级）」，未分店的不随店铺筛选变化。</> },
        { title: "WFS 库存来源", body: data ? data.meta.stores.map((item) => <Tag key={item.sid} bordered={false}>{item.code} · {data.wfs_src[item.sid] || "无"}</Tag>) : "—" },
        { title: "库龄", body: "WFS 库龄按件数分 0–90 / 91–180 / 181–270 / 271–365 / 365 天以上五档，金额 = 件数 × 单件入库成本。" },
      ]}
    />
  );
}

function CashStockBoard() {
  const stock = useStock();
  const data = stock.data;
  const [stores, setStores] = useState<string[]>([]);
  const [view, setView] = useState<View>("inv");

  const codeOf = useMemo(() => new Map((data?.meta.stores ?? []).map((item) => [item.sid, item.code])), [data]);
  const storeTag = (sid: string) => <Tag bordered={false}>{codeOf.get(sid) ?? sid}</Tag>;

  const scoped = useMemo(() => {
    if (!data) return null;
    const inScope = <T extends { sid: string }>(row: T) => !stores.length || stores.includes(row.sid);
    const inv = data.inv_month.filter(inScope);
    const months = [...new Set(inv.map((row) => row.month))].sort().reverse();
    const invRows: InvRow[] = months.map((m) => {
      const xs = inv.filter((row) => row.month === m);
      const goods = sum(xs, (row) => row.goods), head = sum(xs, (row) => row.head), other = sum(xs, (row) => row.other);
      return { m, qty: sum(xs, (row) => row.qty), goods, head, other, total: goods + head + other };
    });
    const wfs = data.wfs.filter(inScope).sort((a, b) => b.amount - a.amount);
    const transit = data.transit.filter(inScope).sort((a, b) => b.amount - a.amount);
    const domestic = data.domestic.filter(inScope).sort((a, b) => b.amount - a.amount);
    const ageAmt = AGE.map((_, i) => sum(wfs, (row) => (row.age[i] || 0) * (row.unit || 0)));
    const ageTotal = sum(ageAmt, (v) => v);
    const ageRows: AgeRow[] = AGE.map((label, i) => ({ label, qty: sum(wfs, (row) => row.age[i] || 0), amount: ageAmt[i], share: ageTotal ? ageAmt[i] / ageTotal : 0 }));
    return { invRows, wfs, transit, domestic, ageRows };
  }, [data, stores]);

  if (!data || !scoped) {
    return (
      <FinanceBoardFrame title="备货资金" loading={stock.isPending} subtitle="建设中 · 读 PMC 的采购 / 在途 / 库存结果（只读）">
        <EmptyState
          title={stock.error ? "本地预览数据未就绪" : "加载中"}
          description={stock.error ? (stock.error as Error).message : "正在读取备货资金数据"}
        />
      </FinanceBoardFrame>
    );
  }

  const du = data.domestic_unassigned;
  const invTotal = sum(scoped.invRows, (row) => row.total);
  const over270 = scoped.ageRows[3].amount + scoped.ageRows[4].amount;
  const cards: ManagementStatCardItem<View>[] = [
    { key: "inv", title: "发货投入（累计）", subtitle: `${scoped.invRows.length} 个发货月 · ${n0(sum(scoped.invRows, (row) => row.qty))} 件`, value: yuan(invTotal), tone: "normal", icon: icon("投") },
    { key: "wfs", title: "WFS 在仓", subtitle: `${n0(sum(scoped.wfs, (row) => row.onhand))} 件在库 · ${scoped.wfs.length} 个 GTIN`, value: yuan(sum(scoped.wfs, (row) => row.amount)), tone: "normal", icon: icon("仓") },
    { key: "age", title: "WFS 库龄超 270 天", subtitle: "点开看五档库龄金额", value: yuan(over270), tone: over270 > 0 ? "warning" : "success", icon: icon("龄") },
    { key: "transit", title: "在途货件（未收货）", subtitle: `${n0(sum(scoped.transit, (row) => row.qty))} 件`, value: yuan(sum(scoped.transit, (row) => row.amount)), tone: "normal", icon: icon("途") },
    { key: "domestic", title: "国内仓", subtitle: `挂店 ${scoped.domestic.length} 批 ${yuan(sum(scoped.domestic, (row) => row.amount))} · 未分店 ${n0(du.batches)} 批`, value: yuan(sum(scoped.domestic, (row) => row.amount) + du.amount), tone: "normal", icon: icon("国") },
  ];

  const invColumns: ProColumns<InvRow>[] = [
    { title: "发货月", dataIndex: "m", width: 110 },
    { title: "件数", dataIndex: "qty", width: 110, align: "right", render: (_, row) => n0(row.qty) },
    { title: "货物 ¥", dataIndex: "goods", width: 160, align: "right", render: (_, row) => <FinMoney value={row.goods} /> },
    { title: "头程 ¥", dataIndex: "head", width: 160, align: "right", render: (_, row) => <FinMoney value={row.head} /> },
    { title: "税 + 辅料 ¥", dataIndex: "other", width: 140, align: "right", render: (_, row) => <FinMoney value={row.other} /> },
    { title: "合计 ¥", dataIndex: "total", width: 170, align: "right", render: (_, row) => <Typography.Text strong><FinMoney value={row.total} /></Typography.Text> },
  ];
  const ageColumns: ProColumns<AgeRow>[] = [
    { title: "库龄", dataIndex: "label", width: 140 },
    { title: "件数", dataIndex: "qty", width: 120, align: "right", render: (_, row) => n0(row.qty) },
    { title: "金额 ¥", dataIndex: "amount", width: 170, align: "right", render: (_, row) => <FinMoney value={row.amount} /> },
    { title: "占比", dataIndex: "share", width: 110, align: "right", render: (_, row) => `${(row.share * 100).toFixed(1)}%` },
  ];
  const wfsColumns: ProColumns<StockWfs>[] = [
    { title: "店铺", dataIndex: "sid", width: 90, render: (_, row) => storeTag(row.sid) },
    { title: "ItemID", dataIndex: "item_id", width: 130, render: (_, row) => row.item_id || "—" },
    { title: "SKU", dataIndex: "sku", width: 120 },
    { title: "GTIN", dataIndex: "gtin", width: 150 },
    { title: "在库", dataIndex: "onhand", width: 80, align: "right", render: (_, row) => n0(row.onhand) },
    { title: "可售", dataIndex: "qty", width: 80, align: "right", render: (_, row) => n0(row.qty) },
    { title: "入库中", dataIndex: "inbound", width: 80, align: "right", render: (_, row) => n0(row.inbound) },
    { title: "超 1 年", key: "old", width: 80, align: "right", render: (_, row) => (row.age[4] ? <Tag color="red" bordered={false}>{n0(row.age[4])}</Tag> : <Typography.Text type="secondary">0</Typography.Text>) },
    { title: "单件成本", dataIndex: "unit", width: 110, align: "right", render: (_, row) => unitCell(row.unit) },
    { title: "占压 ¥", dataIndex: "amount", width: 130, align: "right", render: (_, row) => <Typography.Text strong><FinMoney value={row.amount} /></Typography.Text> },
  ];
  const transitColumns: ProColumns<StockTransit>[] = [
    { title: "店铺", dataIndex: "sid", width: 90, render: (_, row) => storeTag(row.sid) },
    { title: "货件", dataIndex: "cargo", width: 140 },
    { title: "创建日", dataIndex: "date", width: 110 },
    { title: "状态", dataIndex: "status", width: 190, render: (_, row) => <Tag bordered={false}>{row.status}</Tag> },
    { title: "SKU", dataIndex: "sku", width: 120 },
    { title: "未收货", dataIndex: "qty", width: 90, align: "right", render: (_, row) => n0(row.qty) },
    { title: "单件成本", dataIndex: "unit", width: 110, align: "right", render: (_, row) => unitCell(row.unit) },
    { title: "占压 ¥", dataIndex: "amount", width: 130, align: "right", render: (_, row) => <Typography.Text strong><FinMoney value={row.amount} /></Typography.Text> },
  ];
  const domesticColumns: ProColumns<StockDomestic>[] = [
    { title: "店铺", dataIndex: "sid", width: 90, render: (_, row) => storeTag(row.sid) },
    { title: "仓库", dataIndex: "warehouse", width: 150 },
    { title: "批次", dataIndex: "batch", width: 150 },
    { title: "SKU", dataIndex: "sku", width: 120 },
    { title: "数量", dataIndex: "qty", width: 90, align: "right", render: (_, row) => n0(row.qty) },
    { title: "库龄(天)", dataIndex: "age", width: 90, align: "right", render: (_, row) => n0(row.age) },
    { title: "单件成本", dataIndex: "unit", width: 110, align: "right", render: (_, row) => <FinMoney value={row.unit} /> },
    { title: "占压 ¥", dataIndex: "amount", width: 130, align: "right", render: (_, row) => <Typography.Text strong><FinMoney value={row.amount} /></Typography.Text> },
  ];

  return (
    <FinanceBoardFrame
      title="备货资金"
      subtitle={`建设中 · 发货投入（流量）+ 库存货值（存量）· PMC 每日快照 ${data.meta.daily}，只读`}
      toolbar={<>
        <ReportFacetSelect mode="multiple" ariaLabel="店铺" placeholder="全部店铺" unit="店" value={stores} options={data.meta.stores.map((item) => ({ value: item.sid, label: item.code }))} onChange={(value) => setStores((value as string[] | undefined) ?? [])} />
        <Segmented<View> value={view} onChange={setView} options={(Object.keys(VIEW_LABEL) as View[]).map((value) => ({ value, label: VIEW_LABEL[value] }))} />
        <ResetButton onClick={() => { setStores([]); setView("inv"); }} />
      </>}
      summary={<ManagementStatCards<View> ariaLabel="备货资金统计" className="finance-board__summary finance-board__summary--5" cards={cards} activeKey={view} onCardClick={setView} />}
    >
      {view === "inv" && <StockTable<InvRow> label="发货投入表格" rowKey={(row) => row.m} rows={scoped.invRows} columns={invColumns} emptyText="该范围在本次发货单快照里没有发货" />}
      {view === "age" && <StockTable<AgeRow> label="WFS 库龄表格" rowKey={(row) => row.label} rows={scoped.ageRows} columns={ageColumns} emptyText="该范围内没有 WFS 在仓货" />}
      {view === "wfs" && <StockTable<StockWfs> label="WFS 在仓表格" rowKey={(row) => `${row.sid}-${row.gtin}-${row.sku}`} rows={scoped.wfs} columns={wfsColumns} emptyText="该范围内没有 WFS 在仓货" />}
      {view === "transit" && <StockTable<StockTransit> label="在途货件表格" rowKey={(row) => `${row.cargo}-${row.gtin}-${row.sku}`} rows={scoped.transit} columns={transitColumns} emptyText="该范围内没有未收货的货件" />}
      {view === "domestic" && <StockTable<StockDomestic> label="国内仓表格" rowKey={(row) => `${row.batch}-${row.sid}-${row.sku}`} rows={scoped.domestic} columns={domesticColumns} emptyText="该范围内没有挂店铺的国内仓批次" />}
    </FinanceBoardFrame>
  );
}

export default CashStockBoard;

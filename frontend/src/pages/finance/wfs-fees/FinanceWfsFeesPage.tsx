/**
 * 财务 · WFS 费用明细（Rocky 2026-11-12）：一个 tab、一张表、一列费用类型。
 * - 展示已经归属到商品的全部 WFS 费用：结算报表里的服务费各类 + 退货处理费、仓储费、入库运费；配送费不进。
 * - 顶部「导入」上传卖家后台 / 接口下载的原始 CSV（所有店铺都可以）；「同步」走沃尔玛接口（PR 2 开放）；「导出」当前筛选。
 * - 表格上方提示条：和领星账单按 店铺 × 账单期 × 费用类型 核对不一致的；财务看过可以标「已核实」。
 * - 行内「调整」：无 GTIN 的费用改分摊 / 记公司，必填原因，留痕。
 * 全部读写 /api/finance/wfs-fees，没有本地预览数据。
 */
import { Alert, Button, Input, Select, Space, Tag, Tooltip, Typography, message } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import { useMemo, useState } from "react";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import FinanceBoardFrame, { FinMoney } from "@/pages/finance/FinanceBoardFrame";
import BoardTable from "@/pages/finance/payout-recon/BoardTable";
import HelpButton, { type HelpSection } from "@/pages/finance/payout-recon/HelpButton";
import AdjustModal from "./AdjustModal";
import ChecksBar from "./ChecksBar";
import ImportDrawer from "./ImportDrawer";
import { exportLines } from "./wfsExport";
import {
  ATTRIBUTION_TEXT, SOURCE_TEXT, num, useBillPeriods, useFeeTypes, useLines, useSummary, useWfsRefresh, wfsErrorText,
  type ApiLine, type Attribution, type FeeSource, type LineFilter,
} from "./wfsFeesApi";
import "./wfs-fees.css";

const HELP: HelpSection[] = [
  { title: "这页做什么", body: "沃尔玛 WFS 收的各项费用，按店铺、账单期、费用类型落到每个商品（ITEM ID）上，给结算利润、订单审核取数。一张表，「费用类型」一列区分。" },
  { title: "费用范围", body: "结算报表里的服务费（费用返还、丢失赔付、库存调拨、移除、弃置、找回冲回、新卖家补贴返还、仓内损坏赔付、退货中心弃置、预处理、多渠道履约、其他扣费）+ 退货处理费；仓储费（仓储费报表，按 GTIN）；入库运输费（入库运输报告，按货件分到商品）。配送费不进这张表。" },
  { title: "金额", body: "我方视角，美元：正数 = Walmart 付给我们（赔付 / 返还），负数 = 扣费。" },
  { title: "归属", body: "有 GTIN 的按 店铺 + GTIN 对商品表；没有 GTIN 的按规则分摊：入库运费多收退款按该货件的分摊比例，新卖家补贴按明细期间（配送费 = 无逐行折扣原价 × 10%，仓储费 = 各 SKU 仓储费原价 × 10%），仓储费争议退款记公司。基数对不上的标「基数待核」，分摊照样算，金额合计不变。入库运费按货件商品实发数量分（没有实发按申报），货件明细没到之前显示「未分摊」。" },
  { title: "账单期", body: "每笔费用按扣费周（周五）归到领星沃尔玛账单的那一期；按天出账的退货类按交易日；仓储、入库按账期止日。归期依据在明细列里。" },
  { title: "核对", body: "表格上方列出和领星账单对不上的 店铺 × 账单期 × 费用类型。常见原因：期末一天时区差（两期合计相等）、报表漏行、领星没有的新类型。财务核实后点「已核实」写原因，下次金额变了会重新标出。" },
  { title: "导入", body: "所有店铺都可以上传卖家后台下载的原始 CSV（结算报表 / 仓储费报表 / 入库运输报告），系统按内容认类型；结算报表按 Partner ID 认店铺，仓储 / 入库要选店铺。同一份文件再传只刷新不重复；仓储 / 入库同账期重传 = 覆盖，账期交叉但起止不同会拒收。" },
  { title: "调整", body: "无 GTIN 的费用，点「调整」改分摊（分到哪些商品、各多少，合计要等于原金额）或记公司，必填原因，留痕；调整过的行不会被重新导入覆盖。" },
];

const ATTRIBUTION_COLOR: Record<Attribution, string> = { matched: "green", allocated: "blue", allocated_check: "gold", unmatched: "red", unallocated: "orange", company: "default" };
const PAGE_SIZE = 100;

export interface Row extends Omit<ApiLine, "children"> { key: string; storeCode: string; typeName: string; amount: number | null; isChild: boolean; children?: Row[] }

function FinanceWfsFeesPage({ page }: { page: NavigationPage }) {
  const [filter, setFilter] = useState<LineFilter>({ page: 1, page_size: PAGE_SIZE });
  const [q, setQ] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [adjusting, setAdjusting] = useState<Row>();
  const [messageApi, messageHolder] = message.useMessage();
  const types = useFeeTypes();
  const periods = useBillPeriods();
  const lines = useLines(filter);
  const summary = useSummary({ store_id: filter.store_id, report_key: filter.report_key, date_from: filter.date_from, date_to: filter.date_to });
  const refresh = useWfsRefresh();

  const storeCode = useMemo(() => new Map((periods.data ?? []).map((p) => [p.store_id, p.store_code])), [periods.data]);
  const typeName = useMemo(() => new Map((types.data ?? []).map((t) => [t.code, t.name])), [types.data]);
  const stores = useMemo(() => Array.from(storeCode.entries()).sort((a, b) => a[1].localeCompare(b[1])), [storeCode]);
  const periodOptions = useMemo(() => {
    const list = (periods.data ?? []).filter((p) => !filter.store_id || p.store_id === filter.store_id);
    const seen = new Map<string, string>();
    for (const p of list) if (p.report_key) seen.set(p.report_key, `${p.report_date}${filter.store_id ? "" : ` · ${p.store_code}`}${p.period_start_date ? `（${p.period_start_date} ~ ${p.period_end_date}）` : ""}`);
    return Array.from(seen.entries()).map(([value, label]) => ({ value, label })).sort((a, b) => b.label.localeCompare(a.label));
  }, [periods.data, filter.store_id]);

  const toRow = (line: ApiLine, isChild = false): Row => ({
    ...line, key: line.id, storeCode: storeCode.get(line.store_id) ?? line.store_id, typeName: typeName.get(line.fee_type) ?? line.fee_type,
    amount: num(line.amount_usd), isChild, children: line.children.length ? line.children.map((c) => toRow(c, true)) : undefined,
  });
  const rows = useMemo(() => (lines.data?.items ?? []).map((line) => toRow(line)), [lines.data, storeCode, typeName]);  // eslint-disable-line react-hooks/exhaustive-deps
  const set = (patch: Partial<LineFilter>) => setFilter((current) => ({ ...current, ...patch, page: 1 }));

  const columns: ProColumns<Row>[] = [
    { key: "store", title: "店铺", width: 84, fixed: "left", render: (_, row) => (row.isChild ? "" : row.storeCode) },
    { key: "report_date", title: "账单日", width: 100, render: (_, row) => (row.isChild ? "" : row.report_date ?? <Typography.Text type="secondary">未归期</Typography.Text>) },
    { key: "date_charged", title: "扣费日期", width: 100, render: (_, row) => (row.isChild ? "" : row.date_charged) },
    { key: "transaction_date", title: "交易日期", width: 100, render: (_, row) => (row.isChild ? "" : row.transaction_date) },
    { key: "fee_type", title: "费用类型", width: 150, render: (_, row) => (row.isChild ? <Typography.Text type="secondary">└ 分摊</Typography.Text> : <span>{row.typeName}<br /><Typography.Text type="secondary" className="fin-wfs__sub">{row.fee_type}</Typography.Text></span>) },
    { key: "reason_code", title: "Reason", width: 150, ellipsis: true, render: (_, row) => (row.isChild ? "" : row.reason_code || "—") },
    { key: "po", title: "PO / 货件号", width: 130, ellipsis: true, render: (_, row) => row.po_number || "—" },
    { key: "gtin", title: "GTIN", width: 140, render: (_, row) => row.gtin || "—" },
    { key: "item_id", title: "ITEM ID", width: 120, render: (_, row) => row.item_id || "—" },
    { key: "msku", title: "MSKU", width: 140, ellipsis: true, render: (_, row) => row.msku || "—" },
    { key: "local_sku", title: "SKU", width: 110, ellipsis: true, render: (_, row) => row.local_sku || "—" },
    { key: "quantity", title: "数量", width: 70, align: "right", render: (_, row) => (row.quantity ? Number(row.quantity).toLocaleString() : "") },
    { key: "amount", title: "金额（USD）", width: 120, align: "right", render: (_, row) => <FinMoney value={row.amount} cur="USD" /> },
    { key: "attribution", title: "归属", width: 130, render: (_, row) => (row.isChild ? "" : <Tag color={ATTRIBUTION_COLOR[row.attribution]} bordered={false}>{ATTRIBUTION_TEXT[row.attribution]}{row.adjusted ? " · 人工" : ""}</Tag>) },
    { key: "basis", title: "依据", width: 220, ellipsis: true, render: (_, row) => <Tooltip title={row.allocation_basis}>{row.allocation_basis || (row.isChild ? "" : row.bill_match)}</Tooltip> },
    { key: "source", title: "来源", width: 110, render: (_, row) => (row.isChild ? "" : <span>{SOURCE_TEXT[row.fee_source]}{row.missing_since ? <Tag color="default" bordered={false}>重传后消失</Tag> : null}</span>) },
    { key: "detail", title: "说明", width: 260, ellipsis: true, render: (_, row) => (row.isChild ? "" : <Tooltip title={row.detail}>{row.detail || "—"}</Tooltip>) },
    { key: "actions", title: "操作", width: 72, fixed: "right", render: (_, row) => (row.isChild || row.gtin ? null : <Button type="link" size="small" onClick={() => setAdjusting(row)}>调整</Button>) },
  ];

  const total = num(summary.data?.total_amount_usd);
  const toolbar = (
    <>
      <Select allowClear placeholder="店铺" style={{ width: 120 }} value={filter.store_id} options={stores.map(([id, code]) => ({ value: id, label: code }))} onChange={(value) => set({ store_id: value, report_key: undefined })} />
      <Select allowClear showSearch placeholder="账单期" style={{ width: 260 }} value={filter.report_key} options={periodOptions} optionFilterProp="label" onChange={(value) => set({ report_key: value })} />
      <Select allowClear showSearch placeholder="费用类型" style={{ width: 170 }} value={filter.fee_type} optionFilterProp="label" options={(types.data ?? []).map((t) => ({ value: t.code, label: `${t.name} ${t.code}` }))} onChange={(value) => set({ fee_type: value })} />
      <Select allowClear placeholder="来源" style={{ width: 130 }} value={filter.fee_source} options={(Object.keys(SOURCE_TEXT) as FeeSource[]).map((s) => ({ value: s, label: SOURCE_TEXT[s] }))} onChange={(value) => set({ fee_source: value })} />
      <Select allowClear placeholder="归属" style={{ width: 150 }} value={filter.attribution} options={(Object.keys(ATTRIBUTION_TEXT) as Attribution[]).map((a) => ({ value: a, label: ATTRIBUTION_TEXT[a] }))} onChange={(value) => set({ attribution: value })} />
      <Input.Search allowClear placeholder="ITEM ID / MSKU / SKU / GTIN / 货件号" style={{ width: 260 }} value={q} onChange={(e) => setQ(e.target.value)} onSearch={(value) => set({ q: value.trim() || undefined })} />
      <Space className="finance-board__toolbar-actions" size={8}>
        <Tooltip title="按店铺 / 账期从沃尔玛接口拉取报表（下一版开放）"><Button disabled>同步</Button></Tooltip>
        <Button type="primary" onClick={() => setImportOpen(true)}>导入</Button>
        <Button onClick={() => exportLines(rows, typeName)} disabled={!rows.length}>导出 Excel</Button>
      </Space>
    </>
  );
  const subtitle = lines.data ? `${lines.data.total.toLocaleString()} 笔 · 本页 ${lines.data.page}${total != null ? ` · 筛选范围合计 ${total < 0 ? "-" : ""}$${Math.abs(total).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : ""}` : "";

  return (
    <PageShell page={page} headerActions={<HelpButton title="WFS 费用明细" sections={HELP} />}>
      {messageHolder}
      <FinanceBoardFrame title="WFS 费用明细" subtitle={subtitle} preview={false} loading={lines.isPending} toolbar={toolbar}
        summary={<ChecksBar storeId={filter.store_id} reportKey={filter.report_key} storeCode={storeCode} typeName={typeName} onChanged={() => void refresh()} />}>
        {lines.error ? <Alert type="error" showIcon message={wfsErrorText(lines.error)} /> : (
          <BoardTable<Row> label="WFS 费用明细表格" rowKey="key" rows={rows} columns={columns} resizeKey="finance-wfs-fees" pageSize={PAGE_SIZE}
            emptyTitle="没有费用" emptyText={filter.store_id || filter.report_key || filter.fee_type || filter.q ? "当前筛选下没有费用" : "还没有导入或同步任何报表，点右上角「导入」"} />
        )}
        {lines.data && lines.data.total > PAGE_SIZE && (
          <div className="fin-wfs__pager">
            <Button disabled={filter.page <= 1} onClick={() => setFilter((c) => ({ ...c, page: c.page - 1 }))}>上一页</Button>
            <Typography.Text type="secondary">第 {filter.page} / {Math.ceil(lines.data.total / PAGE_SIZE)} 页</Typography.Text>
            <Button disabled={filter.page * PAGE_SIZE >= lines.data.total} onClick={() => setFilter((c) => ({ ...c, page: c.page + 1 }))}>下一页</Button>
          </div>
        )}
      </FinanceBoardFrame>
      <ImportDrawer open={importOpen} stores={stores} onClose={() => setImportOpen(false)} onDone={() => void refresh()} />
      {adjusting && <AdjustModal key={adjusting.id} row={adjusting} onClose={() => setAdjusting(undefined)} onDone={() => { setAdjusting(undefined); void messageApi.success("已调整"); void refresh(); }} />}
    </PageShell>
  );
}

export default FinanceWfsFeesPage;
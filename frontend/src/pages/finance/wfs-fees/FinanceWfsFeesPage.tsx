/**
 * 财务 · WFS 费用明细（Rocky 2026-11-12）：一个 tab、一张表、一列费用类型。
 * - 展示已经归属到商品的全部 WFS 费用：结算报表里的服务费各类 + 退货处理费、仓储费、入库运费；配送费不进。
 * - 顶部「导入」上传卖家后台 / 接口下载的原始 CSV（所有店铺都可以）；「同步」走沃尔玛接口（PR 2 开放）；「导出」当前筛选。
 * - 表格上方提示条：和领星账单按 店铺 × 账单期 × 费用类型 核对不一致的；财务看过可以标「已核实」。
 * - 行内「调整」：无 GTIN 的费用改分摊 / 记公司，必填原因，留痕。
 * 全部读写 /api/finance/wfs-fees，没有本地预览数据。
 */
import { Alert, Button, Input, Space, Tag, Tooltip, Typography, message } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import { SettingOutlined } from "@ant-design/icons";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import { useMemo, useState } from "react";
import PageShell from "@/components/page/PageShell";
import { REPORT_TABLE_DEFAULT_PAGE_SIZE } from "@/components/report-table/pagination";
import ResetButton from "@/components/report-table/ResetButton";
import ReportFacetSelect from "@/shared/report-filters";
import type { NavigationPage } from "@/config/navigation";
import FinanceBoardFrame, { FinMoney } from "@/pages/finance/FinanceBoardFrame";
import BoardTable from "@/pages/finance/payout-recon/BoardTable";
import HelpButton, { type HelpSection } from "@/pages/finance/payout-recon/HelpButton";
import AdjustModal from "./AdjustModal";
import ChecksBar from "./ChecksBar";
import ImportDrawer from "./ImportDrawer";
import { WFS_COLUMN_GROUPS, WFS_DEFAULT_KEYS, WFS_FIXED_KEYS, readWfsColumns, writeWfsColumns } from "./wfsColumns";
import { exportLines } from "./wfsExport";
import {
  ATTRIBUTION_GROUP, ATTRIBUTION_GROUP_TEXT, ATTRIBUTION_TEXT, SOURCE_TEXT, SPLIT_TEXT, attributionParam, detailText, num, reasonText, useBillPeriods, useFeeTypes, useLines, useSummary, useWfsRefresh, wfsErrorText,
  type ApiLine, type AttributionGroup, type FeeSource, type LineFilter,
} from "./wfsFeesApi";
import "./wfs-fees.css";

const HELP: HelpSection[] = [
  { title: "这页做什么", body: "沃尔玛 WFS 收的各项费用，按店铺、账单期、费用类型落到每个商品（ITEM ID）上，给结算利润、订单审核取数。一张表，「费用类型」一列区分。" },
  { title: "费用范围", body: "结算报表里的服务费（费用返还、丢失赔付、库存调拨、移除、弃置、找回冲回、新卖家补贴返还、仓内损坏赔付、退货中心弃置、预处理、多渠道履约、其他扣费）+ 退货处理费；仓储费（仓储费报表，按 GTIN）；入库运输费（入库运输报告，按货件分到商品）。配送费不进这张表。" },
  { title: "金额", body: "我方视角，美元：正数 = Walmart 付给我们（赔付 / 返还），负数 = 扣费。" },
  { title: "归属", body: "三档：已到商品（GTIN 对上商品，或按规则分摊到了商品）、待处理（GTIN 对不上、等货件明细还没分摊、分摊基数对不上待核）、记公司（不分到商品，比如仓储费争议退款）。细分原因在「依据」列。分摊规则：入库运费按货件商品实发数量分（没有实发按申报），入库运费多收退款按该货件的比例分，新卖家补贴按明细期间（配送费 = 无逐行折扣原价 × 10%，仓储费 = 各 SKU 仓储费原价 × 10%）。" },
  { title: "分摊行", body: "一笔费用分到多个商品时，表里按分到的商品一行一行列（店铺、日期、类型、货件号同原行，商品和金额是各自的），「分摊」列标 第几份/共几份，几份合计 = 原金额。导出也是这样。" },
  { title: "账单期", body: "每笔费用按扣费周（周五）归到领星沃尔玛账单的那一期；按天出账的退货类按交易日；仓储、入库按账期止日。归期依据在明细列里。" },
  { title: "核对", body: "表格上方列出和领星账单对不上的 店铺 × 账单期 × 费用类型。常见原因：期末一天时区差（两期合计相等）、报表漏行、领星没有的新类型。财务核实后点「已核实」写原因，下次金额变了会重新标出。" },
  { title: "导入", body: "所有店铺都可以上传卖家后台下载的原始 CSV 或 ZIP（结算报表 / 仓储费报表 / 入库运输报告），不用选店铺、账期：系统按内容认类型，按 Partner ID 和文件里的商品自动认店，账期取报表自带的。认不出店（比如多店共有的商品、入库运输报告）才会在那一行让你选店重传。同一份文件再传只刷新不重复，已导入到别的店的文件会拒收；仓储 / 入库同账期重传 = 覆盖，账期交叉但起止不同会拒收。" },
  { title: "调整", body: "无 GTIN 的费用，点「调整」改分摊（分到哪些商品、各多少，合计要等于原金额）或记公司，必填原因，留痕；调整过的行不会被重新导入覆盖。" },
];

/** 中文在上、原始英文在下（小字浅色）——页面上所有报表原文都这样显示（Rocky 11-13） */
const Bi = ({ zh, en }: { zh: string; en?: string }) => (
  <span className="fin-wfs__bi">{zh}{en && en !== zh ? <><br /><Typography.Text type="secondary" className="fin-wfs__sub">{en}</Typography.Text></> : null}</span>
);

const GROUP_COLOR: Record<AttributionGroup, string> = { done: "green", todo: "orange", company: "default" };
const PAGE_SIZE = REPORT_TABLE_DEFAULT_PAGE_SIZE;

/**
 * 表格一行：原行没有分摊就是它自己；有分摊的原行不单独显示，按分摊子行展开成多行，
 * 每行带原行的店铺 / 日期 / 类型 / 货件号，商品和金额是子行自己的（合计 = 原行）；「分摊」列标 第几份/共几份。
 */
export interface Row extends Omit<ApiLine, "children"> {
  key: string; storeCode: string; typeName: string; amount: number | null;
  /** 原行 id（分摊行调整时用） */
  parentId: string; share?: string; shareBasis?: string;
}

function FinanceWfsFeesPage({ page }: { page: NavigationPage }) {
  const [filter, setFilter] = useState<LineFilter>({ page: 1, page_size: PAGE_SIZE });
  const [q, setQ] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [adjusting, setAdjusting] = useState<Row>();
  const [columnKeys, setColumnKeys] = useState<string[]>(readWfsColumns);
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const applyColumns = (keys: string[]) => { setColumnKeys(keys); writeWfsColumns(keys); setColumnConfigOpen(false); };
  // 筛选都可多选（Rocky 11-13）：页面上存数组，传接口时逗号拼接
  const [picked, setPicked] = useState<{ stores: string[]; periods: string[]; types: string[]; sources: FeeSource[]; groups: AttributionGroup[]; splits: string[] }>({ stores: [], periods: [], types: [], sources: [], groups: [], splits: [] });
  const join = (values: string[]) => (values.length ? values.join(",") : undefined);
  const [messageApi, messageHolder] = message.useMessage();
  const types = useFeeTypes();
  const periods = useBillPeriods();
  const lines = useLines(filter);
  const adjustingLine = adjusting ? (lines.data?.items ?? []).find((l) => l.id === adjusting.parentId) : undefined;
  const summary = useSummary(filter);
  const refresh = useWfsRefresh();

  const storeCode = useMemo(() => new Map((periods.data ?? []).map((p) => [p.store_id, p.store_code])), [periods.data]);
  const typeName = useMemo(() => new Map((types.data ?? []).map((t) => [t.code, t.name])), [types.data]);
  const stores = useMemo(() => Array.from(storeCode.entries()).sort((a, b) => a[1].localeCompare(b[1])), [storeCode]);
  const periodOptions = useMemo(() => {
    const list = (periods.data ?? []).filter((p) => !picked.stores.length || picked.stores.includes(p.store_id));
    const seen = new Map<string, string>();
    for (const p of list) if (p.report_key) seen.set(p.report_key, `${p.report_date}${picked.stores.length === 1 ? "" : ` · ${p.store_code}`}${p.period_start_date ? `（${p.period_start_date} ~ ${p.period_end_date}）` : ""}`);
    return Array.from(seen.entries()).map(([value, label]) => ({ value, label })).sort((a, b) => b.label.localeCompare(a.label));
  }, [periods.data, picked.stores]);

  const toRows = (line: ApiLine): Row[] => {
    const { children, ...parent } = line;
    const base = { ...parent, storeCode: storeCode.get(line.store_id) ?? line.store_id, typeName: typeName.get(line.fee_type) ?? line.fee_type, parentId: line.id };
    if (!children.length) return [{ ...base, key: line.id, amount: num(line.amount_usd) }];
    return children.map((c, i) => ({
      ...base, key: c.id, gtin: c.gtin, item_id: c.item_id, msku: c.msku, local_sku: c.local_sku, quantity: c.quantity,
      amount: num(c.amount_usd), share: `${i + 1}/${children.length}`, shareBasis: c.allocation_basis,
    }));
  };
  const rows = useMemo(() => (lines.data?.items ?? []).flatMap((line) => toRows(line)), [lines.data, storeCode, typeName]);  // eslint-disable-line react-hooks/exhaustive-deps
  const set = (patch: Partial<LineFilter>) => setFilter((current) => ({ ...current, ...patch, page: 1 }));

  const columns: ProColumns<Row>[] = [
    { key: "store", title: "店铺", width: 84, fixed: "left", render: (_, row) => row.storeCode },
    { key: "report_date", title: "账单日", width: 100, render: (_, row) => row.report_date ?? <Typography.Text type="secondary">未归期</Typography.Text> },
    { key: "date_charged", title: "扣费日期", width: 100, render: (_, row) => row.date_charged },
    { key: "transaction_date", title: "交易日期", width: 100, render: (_, row) => row.transaction_date },
    { key: "fee_type", title: "费用类型", width: 150, render: (_, row) => <Bi zh={row.typeName} en={row.fee_type} /> },
    { key: "reason_code", title: "原因", width: 170, render: (_, row) => (row.reason_code ? <Bi zh={reasonText(row.reason_code)} en={row.reason_code} /> : "—") },
    { key: "po", title: "订单 / 货件号", width: 130, ellipsis: true, render: (_, row) => row.po_number || "—" },
    { key: "gtin", title: "商品条码", width: 140, render: (_, row) => row.gtin || "—" },
    { key: "item_id", title: "商品 ID", width: 120, render: (_, row) => row.item_id || "—" },
    { key: "msku", title: "店铺 SKU", width: 140, ellipsis: true, render: (_, row) => row.msku || "—" },
    { key: "local_sku", title: "本地 SKU", width: 110, ellipsis: true, render: (_, row) => row.local_sku || "—" },
    { key: "quantity", title: "数量", width: 70, align: "right", render: (_, row) => (row.quantity ? Number(row.quantity).toLocaleString() : "") },
    { key: "amount", title: "金额（USD）", width: 120, align: "right", render: (_, row) => <FinMoney value={row.amount} cur="USD" /> },
    { key: "share", title: "分摊", width: 80, render: (_, row) => (row.share ? <Tooltip title={row.shareBasis}>{row.share}</Tooltip> : "") },
    { key: "attribution", title: "归属", width: 100, render: (_, row) => <Tag color={GROUP_COLOR[ATTRIBUTION_GROUP[row.attribution]]} bordered={false}>{ATTRIBUTION_GROUP_TEXT[ATTRIBUTION_GROUP[row.attribution]]}{row.adjusted ? " · 人工" : ""}</Tag> },
    { key: "basis", title: "依据", width: 240, ellipsis: true, render: (_, row) => { const text = [ATTRIBUTION_TEXT[row.attribution], row.allocation_basis, row.bill_match].filter(Boolean).join(" · "); return <Tooltip title={text}>{text}</Tooltip>; } },
    { key: "source", title: "来源", width: 110, render: (_, row) => <span>{SOURCE_TEXT[row.fee_source]}{row.missing_since ? <Tag color="default" bordered={false}>重传后消失</Tag> : null}</span> },
    { key: "detail", title: "说明", width: 300, render: (_, row) => (row.detail ? <Tooltip title={row.detail}><Bi zh={detailText(row.detail)} en={row.detail} /></Tooltip> : "—") },
    { key: "actions", title: "操作", width: 72, fixed: "right", render: (_, row) => (row.share || !row.gtin ? <Button type="link" size="small" onClick={() => setAdjusting(row)}>调整</Button> : null) },
  ];

  // 按列配置的顺序和显示与否取列（店铺、操作固定）
  const shownColumns = [...new Set([...columnKeys, "actions"])].map((key) => columns.find((c) => c.key === key)).filter((c): c is ProColumns<Row> => Boolean(c));
  const total = num(summary.data?.total_amount_usd);
  const pageTotal = rows.reduce((sum, row) => sum + (row.amount ?? 0), 0);
  const totalQuantity = num(summary.data?.total_quantity);
  const pageQuantity = rows.reduce((sum, row) => sum + (num(row.quantity) ?? 0), 0);
  const toolbar = (
    <>
      <ReportFacetSelect mode="multiple" ariaLabel="店铺" placeholder="店铺" unit="家" value={picked.stores}
        options={stores.map(([value, label]) => ({ value, label }))}
        onChange={(value) => { const next = (value as string[] | undefined) ?? []; setPicked((c) => ({ ...c, stores: next, periods: [] })); set({ store_id: join(next), report_key: undefined }); }} />
      <ReportFacetSelect mode="multiple" ariaLabel="账单期" placeholder="账单期" unit="期" value={picked.periods} popupWidth={320}
        options={periodOptions}
        onChange={(value) => { const next = (value as string[] | undefined) ?? []; setPicked((c) => ({ ...c, periods: next })); set({ report_key: join(next) }); }} />
      <ReportFacetSelect mode="multiple" ariaLabel="费用类型" placeholder="费用类型" unit="类" value={picked.types}
        options={(types.data ?? []).map((t) => ({ value: t.code, label: t.name }))}
        onChange={(value) => { const next = (value as string[] | undefined) ?? []; setPicked((c) => ({ ...c, types: next })); set({ fee_type: join(next) }); }} />
      <ReportFacetSelect mode="multiple" ariaLabel="来源" placeholder="来源" unit="种" value={picked.sources} showSearch={false}
        options={(Object.keys(SOURCE_TEXT) as FeeSource[]).map((value) => ({ value, label: SOURCE_TEXT[value] }))}
        onChange={(value) => { const next = (value as FeeSource[] | undefined) ?? []; setPicked((c) => ({ ...c, sources: next })); set({ fee_source: join(next) }); }} />
      <ReportFacetSelect mode="multiple" ariaLabel="归属" placeholder="归属" unit="档" value={picked.groups} showSearch={false}
        options={(Object.keys(ATTRIBUTION_GROUP_TEXT) as AttributionGroup[]).map((value) => ({ value, label: ATTRIBUTION_GROUP_TEXT[value] }))}
        onChange={(value) => { const next = (value as AttributionGroup[] | undefined) ?? []; setPicked((c) => ({ ...c, groups: next })); set({ attribution: attributionParam(next) }); }} />
      <ReportFacetSelect mode="multiple" ariaLabel="分摊" placeholder="分摊" unit="种" value={picked.splits} showSearch={false}
        options={(Object.keys(SPLIT_TEXT) as ("yes" | "no")[]).map((value) => ({ value, label: SPLIT_TEXT[value] }))}
        onChange={(value) => { const next = (value as string[] | undefined) ?? []; setPicked((c) => ({ ...c, splits: next })); set({ split: join(next) }); }} />
      <Input.Search allowClear placeholder="商品 ID / SKU / 条码 / 货件号" style={{ width: 260 }} value={q} onChange={(e) => setQ(e.target.value)} onSearch={(value) => set({ q: value.trim() || undefined })} />
      <ResetButton onClick={() => { setQ(""); setPicked({ stores: [], periods: [], types: [], sources: [], groups: [], splits: [] }); setFilter({ page: 1, page_size: PAGE_SIZE }); }} />
      <Space className="finance-board__toolbar-actions" size={8}>
        <Tooltip title="按店铺 / 账期从沃尔玛接口拉取报表（下一版开放）"><Button disabled>同步</Button></Tooltip>
        <Button type="primary" onClick={() => setImportOpen(true)}>导入</Button>
        <Tooltip title="导出当前这一页的行（含分摊行）；要导更多请加筛选"><Button onClick={() => exportLines(rows, typeName)} disabled={!rows.length}>导出本页</Button></Tooltip>
        <Button aria-label="列配置" icon={<SettingOutlined aria-hidden="true" />} onClick={() => setColumnConfigOpen(true)} />
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
          <BoardTable<Row> label="WFS 费用明细表格" rowKey="key" rows={rows} columns={shownColumns} resizeKey="finance-wfs-fees" pageSize={PAGE_SIZE}
            serverPage={{ current: filter.page, pageSize: filter.page_size, total: lines.data?.total ?? 0, onChange: (page, pageSize) => setFilter((c) => ({ ...c, page: pageSize === c.page_size ? page : 1, page_size: pageSize })) }}
            totals={{
              store: <Typography.Text strong>合计</Typography.Text>,
              quantity: (
                <span>{totalQuantity == null ? "—" : totalQuantity.toLocaleString()}<br /><Typography.Text type="secondary" className="fin-wfs__sub">本页 {pageQuantity.toLocaleString()}</Typography.Text></span>
              ),
              amount: (
                <Tooltip title={`全部筛选结果合计；本页 ${rows.length} 行合计 ${pageTotal.toFixed(2)}`}>
                  <span><FinMoney value={total} cur="USD" /><br /><Typography.Text type="secondary" className="fin-wfs__sub">本页 {pageTotal.toFixed(2)}</Typography.Text></span>
                </Tooltip>
              ),
            }}
            emptyTitle="没有费用" emptyText={filter.store_id || filter.report_key || filter.fee_type || filter.q ? "当前筛选下没有费用" : "还没有导入或同步任何报表，点右上角「导入」"} />
        )}
      </FinanceBoardFrame>
      <ImportDrawer open={importOpen} stores={stores} onClose={() => setImportOpen(false)} onDone={() => void refresh()} />
      <RuntimeColumnConfigDrawer open={columnConfigOpen} groups={WFS_COLUMN_GROUPS} fixedKeys={WFS_FIXED_KEYS} defaultKeys={WFS_DEFAULT_KEYS} appliedKeys={columnKeys} onApply={applyColumns} onClose={() => setColumnConfigOpen(false)} onSaveTemplate={() => void messageApi.info("列模板暂未开放；当前列配置只保存在本浏览器")} />
      {adjusting && adjustingLine && <AdjustModal key={adjustingLine.id} row={adjustingLine} title={`调整归属 · ${adjusting.storeCode} · ${adjusting.typeName} · ${adjusting.date_charged}`} onClose={() => setAdjusting(undefined)} onDone={() => { setAdjusting(undefined); void messageApi.success("已调整"); void refresh(); }} />}
    </PageShell>
  );
}

export default FinanceWfsFeesPage;

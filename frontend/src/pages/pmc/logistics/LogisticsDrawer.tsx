/** 发货单详情（8088 SpDrawer）：时间线 / 系统内物流时间 / Walmart 回读 / 物流商轨迹 / 货件 × 产品 / 异常。 */
import { Alert, Descriptions, Drawer, Empty, Spin, Table, Tag, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { BackendRequestError } from "@/api/backendApi";
import { getShippingList, type LogisticsDetail, type LogisticsGood, type LogisticsRow } from "./logisticsApi";
import { ARR_SRC, fmt, money } from "./logisticsFormat";
import { SevTag, SignGap, StageTag } from "./logisticsShared";

const { Text } = Typography;

const PLAN_SRC: Record<string, string> = {
  carrier_est: "众壹最新「预计美国时间 X 派送入仓」",
  "ata+cycle": "实际到港 + 周期",
  "atd+voyage+cycle": "实际开船 + 航程 + 周期",
  "eta+cycle": "预计到港 + 周期",
  lx_arrival: "领星 arrival_time",
  region_total: "发货日 + 地区兜底天数",
};

function steps(s: LogisticsRow, buffer: number) {
  return [
    { t: "提货 / 发货", plan: s.t.delivery, act: s.pickup, note: "众壹「货物进入操作中心」，无则领星实际发货 / 发货时间；合同时效从提货次日起算" },
    { t: "开船", plan: "", act: s.atd, note: "众壹「已开船」，无则领星 sail_time（开船只看实际）" },
    { t: "到港", plan: s.eta, act: s.ata, note: "预计 = 领星 expected_arrival_time，无则众壹「预计到港时间」；实际 = 众壹「已靠港」" },
    {
      t: "到仓",
      plan: s.arrivalPlan,
      act: s.arrivalActual,
      note: `实际 = 众壹「签收完成」与 Walmart 签收取早（${ARR_SRC[s.arrivalActualSrc] ?? "—"}）；预计 = ${PLAN_SRC[s.arrivalPlanSrc] ?? "无"}（周期 ${s.cyc ?? "—"} 天${s.cycSrc === "region" ? "，地区兜底" : ""}）`,
    },
    { t: "Walmart 开始收货", plan: "", act: s.wmReceiptStart || s.wmFirstReceive, note: s.wmReceiptStart ? "Walmart inventory-log 最早 Receipt" : "领星 to_receive_time" },
    {
      t: "可售（首批上架）",
      plan: s.sellableSrc !== "real" ? s.sellableDate : "",
      act: s.sellableSrc === "real" ? s.sellableDate : "",
      note: s.sellableSrc === "real" ? `首批上架即可售${s.wmReceiptDone ? `；收货完成 ${s.wmLastReceipt}` : ""}` : `还没上架：预计可售 = 到仓日 + 缓冲 ${buffer} 天`,
    },
    { t: "Walmart 签收 / Closed", plan: "", act: s.wmActualDelivery || s.wmClosed, note: s.wmActualDelivery ? "Walmart actualDeliveryDate" : "领星 to_closed_time" },
  ];
}

const goodsColumns = (s: LogisticsRow) => [
  { title: "SKU / MSKU", width: 150, render: (_: unknown, g: LogisticsGood) => <span><b>{g.sku}</b><br /><Text type="secondary">{g.msku}</Text></span> },
  { title: "GTIN", dataIndex: "gtin", width: 140, render: (v: string) => v || "—" },
  { title: "店铺", dataIndex: "store", width: 200 },
  { title: "申报量", dataIndex: "apply", width: 80, align: "right" as const, render: fmt },
  { title: "发货量", dataIndex: "qty", width: 80, align: "right" as const, render: fmt },
  { title: "箱数", dataIndex: "boxes", width: 70, align: "right" as const },
  { title: "单箱数", dataIndex: "per", width: 70, align: "right" as const },
  { title: "箱毛重 KG", dataIndex: "box_kg", width: 90, align: "right" as const, render: (v: string) => (v ? Number(v).toFixed(2) : "—") },
  {
    title: "货件号",
    width: 170,
    render: (_: unknown, g: LogisticsGood) => {
      const c = s.cargos.find((x) => x.code === g.cargo);
      return <span>{g.cargo || "—"}{c && <><br /><Text type="secondary">{c.status}{c.status === "CLOSED" ? ` 实收 ${c.received}/${c.declare}` : ""}</Text></>}</span>;
    },
  },
  { title: "品名", dataIndex: "name" },
  { title: "头程/件", dataIndex: "head_cost", width: 110, align: "right" as const, render: (v: number, g: LogisticsGood) => (v ? `${money(v)} ${g.value_source}` : "—") },
];

function Body({ d, buffer, deliveredNotSigned }: { d: LogisticsDetail; buffer: number; deliveredNotSigned: number }) {
  const s = d.row;
  const tr = d.track;
  const items = steps(s, buffer);
  return (
    <div className="logi-detail">
      <Descriptions size="small" bordered column={4} items={[
        { key: "store", label: "店铺", children: s.stores.join(" / ") || "—" },
        { key: "boxes", label: "总箱数", children: fmt(s.boxes) },
        { key: "wt", label: "计费重", children: s.chargeWeight ? `${fmt(s.chargeWeight)} kg（众壹）` : `${s.gw} kg（领星毛重）` },
        { key: "gap", label: "到货 vs Walmart 签收", children: <SignGap s={s} today={d.today} /> },
        { key: "track", label: "运单号", children: s.tracking.join(", ") || "缺失" },
        { key: "cost", label: "实际费用（领星）", children: s.cost.transport || s.cost.other ? `${money(s.cost.transport, s.cost.currency)} 运费 + ${money(s.cost.other, s.cost.currency)} 其他` : "未录入" },
        { key: "fee", label: "计费方式", children: s.fee_type || "—" },
        {
          key: "ct",
          label: "合同时效 / 已用 / 剩余",
          children: s.ct
            ? `${s.ct} 天（${s.region}）/ ${s.usedDays ?? "—"} 天 / ${s.remain == null ? "—" : s.remain < 0 ? `超 ${-s.remain} 天` : `${s.remain} 天`}${s.penalty ? ` · 可索赔 ¥${s.penalty}` : ""}`
            : "未设置",
        },
      ]} />
      <h4>物流时间线 <Text type="secondary">有实际取实际，否则取预计 · 到仓日期 = {s.arrivalDate || "—"}</Text></h4>
      <ul className="logi-timeline">
        {items.map((x) => (
          <li key={x.t} className={x.act ? "is-done" : undefined}>
            <span className="logi-timeline__t">{x.t}</span>
            <span>
              {x.act ? <b>实际 {x.act}</b> : x.plan ? <>预计 {x.plan}</> : <Text type="secondary">无</Text>}
              {x.act && x.plan && x.plan !== x.act ? <Text type="secondary">（预计 {x.plan}）</Text> : null}
              {" "}<Text type="secondary">{x.note}</Text>
            </span>
          </li>
        ))}
      </ul>
      <h4>系统内物流时间 <Text type="secondary">不写回领星；右列领星现值仅供对账</Text></h4>
      <Table size="small" pagination={false} rowKey="f" dataSource={[
        { f: "实际发货时间 actual_delivery_time", v: tr?.nodes?.opc ?? "", lx: s.t.actual_delivery },
        { f: "开船时间 sail_time", v: tr?.nodes?.atd ?? "", lx: s.t.sail },
        { f: "预计到港时间 expected_arrival_time", v: tr?.nodes?.eta ?? "", lx: s.t.expected_arrival },
        { f: "预计到货时间", v: s.arrivalPlan, lx: s.t.arrival },
        { f: "实际到货时间", v: s.arrivalActual, lx: s.t.actual_due },
      ]} columns={[
        { title: "字段", dataIndex: "f", width: 260 },
        { title: "系统值", dataIndex: "v", width: 120, render: (v: string) => v || "—" },
        { title: "领星现值", dataIndex: "lx", width: 120, render: (v: string) => v || "空" },
        {
          title: "对账",
          width: 120,
          render: (_: unknown, x: { f: string; v: string; lx: string }) =>
            !x.v ? <Tag bordered={false}>轨迹未到</Tag> : x.v === x.lx ? <Tag color="success" bordered={false}>一致</Tag> : x.lx ? <Tag color="warning" bordered={false}>与领星不同</Tag> : <Tag bordered={false}>领星空</Tag>,
        },
      ]} />
      {d.walmart.length > 0 && (
        <Alert type="info" style={{ marginTop: 8 }} message={`Walmart 回读：${d.walmart.map((x) => `${x.code} ${x.status} · 签收 ${x.actualDelivery || "无"} · 首次 Receipt ${x.firstReceipt || "—"} · 最后 Receipt ${x.lastReceipt || "—"} · Receipt 合计 ${x.receiptUnits} / receivedUnits ${x.receivedUnits}`).join("；")}`} />
      )}
      <h4>物流商轨迹 {tr ? <Text type="secondary">众壹 · 运单 {tr.number} · 客户单号 {tr.customerNumber} · {tr.status} · 计费重 {tr.totalWeightKg} kg</Text> : <Text type="secondary">该发货单无物流商轨迹（{s.provider || "—"}{s.tracking.length ? "" : " · 无运单号"}）</Text>}</h4>
      {tr && (
        <Table size="small" pagination={{ pageSize: 10, size: "small" }} rowKey={(r) => `${r.t}-${r.cn}`} dataSource={tr.tracks ?? []} columns={[
          { title: "轨迹时间", dataIndex: "t", width: 160 },
          { title: "中文轨迹", dataIndex: "cn", render: (v: string) => (["签收完成", "已靠港，正在卸柜中", "已开船", "货物进入操作中心"].includes(v) ? <b>{v}</b> : v) },
          { title: "英文轨迹", dataIndex: "en" },
        ]} />
      )}
      <h4>货件 × 产品 <Text type="secondary">{s.cargos.length} 个货件 · {s.goods.length} 行 · 申报 {fmt(s.declared)} / 实收 {fmt(s.received)}</Text></h4>
      <Table size="small" pagination={false} rowKey={(_, i) => String(i)} dataSource={s.goods} columns={goodsColumns(s)} scroll={{ x: 1300 }} locale={{ emptyText: "无商品行" }} />
      {s.ex.length > 0 && (
        <>
          <h4>异常 / 提醒 <Text type="secondary">阈值：物流签收后 Walmart 未签收 {deliveredNotSigned} 天</Text></h4>
          {s.ex.map((e, i) => <div key={i} className="logi-exrow"><SevTag sev={e.sev} /> <b>{e.type}</b> · {e.desc}</div>)}
        </>
      )}
    </div>
  );
}

export default function LogisticsDrawer({ code, scope, buffer, deliveredNotSigned, onClose }: {
  code: string;
  scope: string;
  buffer: number;
  deliveredNotSigned: number;
  onClose: () => void;
}) {
  const q = useQuery({
    queryKey: ["pmc-logistics", scope, "detail", code],
    queryFn: ({ signal }) => getShippingList(code, signal),
    retry: false,
  });
  const d = q.data?.data;
  return (
    <Drawer open width={1100} onClose={onClose} title={<span>发货单 {code} {d && <StageTag stage={d.row.stage} />} {d && <Text type="secondary">{d.row.provider} · {d.row.channel}{d.row.method ? ` · ${d.row.method}` : ""} · {d.row.fc} {d.row.region}</Text>}</span>}>
      {q.isLoading && <Spin />}
      {q.error && <Alert type="error" showIcon message={q.error instanceof BackendRequestError && q.error.status === 404 ? "发货单不存在或不在当前数据范围" : "发货单详情加载失败，请重试"} />}
      {d ? <Body d={d} buffer={buffer} deliveredNotSigned={deliveredNotSigned} /> : !q.isLoading && !q.error && <Empty />}
    </Drawer>
  );
}

/** 发货单详情就地展开（不再弹出第二层抽屉）：到货预测明细里点「展开」时用（Rocky 2026-11-04）。 */
export function LogisticsInlineDetail({ code, scope, buffer, deliveredNotSigned }: {
  code: string;
  scope: string;
  buffer: number;
  deliveredNotSigned: number;
}) {
  const q = useQuery({
    queryKey: ["pmc-logistics", scope, "detail", code],
    queryFn: ({ signal }) => getShippingList(code, signal),
    retry: false,
  });
  const d = q.data?.data;
  return (
    <div className="logi-inline-detail" aria-label={`发货单 ${code} 详情`}>
      {q.isLoading && <Spin />}
      {q.error && <Alert type="error" showIcon message={q.error instanceof BackendRequestError && q.error.status === 404 ? "发货单不存在或不在当前数据范围" : "发货单详情加载失败，请重试"} />}
      {d && (
        <>
          <div className="logi-inline-detail__head">
            <b>发货单 {code}</b> <StageTag stage={d.row.stage} />{" "}
            <Text type="secondary">{d.row.provider} · {d.row.channel}{d.row.method ? ` · ${d.row.method}` : ""} · {d.row.fc} {d.row.region}</Text>
          </div>
          <Body d={d} buffer={buffer} deliveredNotSigned={deliveredNotSigned} />
        </>
      )}
    </div>
  );
}

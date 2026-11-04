/** ItemID detail drawer: store split, stock-out timeline, supply batches, domestic batches, issues, replenishment. */
import { Alert, Drawer, Space, Tag, Typography } from "antd";
import type { ReactNode } from "react";
import { StatusTagCell, WalmartItemLink } from "@/components/report-table/cells";
import OverviewDetailTable from "@/pages/pmc/overview/components/OverviewDetailTable";
import { addDays, CAT_COLOR, coverFallback, fmt, fmt1, KIND } from "@/pages/pmc/overview/overviewDisplay";
import type { OverviewBatch, OverviewDomesticRow, OverviewItemDetail, OverviewStoreShare } from "@/pages/pmc/overview/overviewTypes";

const Muted = ({ children }: { children: ReactNode }) => <Typography.Text type="secondary">{children}</Typography.Text>;

const KV = ({ k, v }: { k: string; v: ReactNode }) => (
  <div className="pmc-overview__kv"><span>{k}</span><strong>{v === null || v === undefined || v === "" ? "—" : v}</strong></div>
);

type StoreRow = OverviewStoreShare & Record<string, unknown>;
type BatchRow = OverviewBatch & Record<string, unknown>;
type DomRow = OverviewDomesticRow & Record<string, unknown>;

interface OverviewItemDrawerProps {
  item: OverviewItemDetail;
  today: string;
  params: Record<string, number>;
  onClose: () => void;
}

function OverviewItemDrawer({ item: r, today, params: p, onClose }: OverviewItemDrawerProps) {
  const batches = r.batches.filter((b) => b.qty > 0) as BatchRow[];
  const domesticDays = p.domesticDays ?? 7;
  const salesMinDays = p.salesMinDays ?? 14;
  return (
    <Drawer
      open
      width="min(960px, calc(100vw - 24px))"
      onClose={onClose}
      title={(
        <Space size={6} wrap>
          <WalmartItemLink itemId={r.item_id} />
          <span>{r.sku} · {r.name}</span>
          <StatusTagCell label={r.main} color={CAT_COLOR[r.main] ?? "success"} />
        </Space>
      )}
    >
      <div className="pmc-overview__drawer">
        <h4>店铺分布</h4>
        <OverviewDetailTable<StoreRow>
          label="店铺分布"
          rowKey="id"
          rows={r.stores as StoreRow[]}
          columns={[
            { title: "店铺", key: "name", render: (_, s) => s.name },
            { title: "近 30 天销量", key: "sales30", align: "right", render: (_, s) => fmt(s.sales30) },
            { title: "WFS 可售", key: "available", align: "right", render: (_, s) => fmt(s.available) },
            { title: "在途（该店铺发起）", key: "intransit", align: "right", render: (_, s) => fmt(s.intransit) },
          ]}
        />
        <h4>断货时间线</h4>
        <div className="pmc-overview__kv-grid">
          <KV k="日销" v={r.no_stock_90 ? "近 90 天无库存" : `${fmt1(r.daily)} 件/天（最近 ${r.n30} 个有货日，回看 ${r.n_window ?? "—"} 天）`} />
          <KV k="断货天数" v={r.oos_days === null ? "90 天以上" : r.oos_days > 0 ? `${r.oos_days} 天（最后有货日 ${addDays(today, -r.oos_days - 1)}）` : "未断货"} />
          <KV k="全链路有效供应" v={`${fmt(r.supply)} 件`} />
          <KV k="现有可售能卖到" v={r.sellout ?? (r.daily > 0 ? "400 天内不断货" : "无销量")} />
          <KV k="下一批预计可售" v={r.next_date ?? "无来货"} />
          <KV k="预计断货天数" v={r.gap_days !== null ? `${r.gap_days} 天（${r.resume} 恢复）` : r.sellout ? "之后无来货" : "—"} />
          <KV k="库存覆盖天数" v={r.cover !== null ? `${fmt(r.cover)} 天 · ${r.over}` : coverFallback(r, salesMinDays)} />
          <KV k="提前期" v={`${fmt1(r.lead_total)} 天（采购交期 ${fmt1(r.lead_p)}）`} />
          <KV k="补货周期" v={`${r.cycle_days ?? "—"} 天`} />
        </div>
        <h4>供应链批次（互斥口径，按预计可售日）</h4>
        <OverviewDetailTable<BatchRow>
          label="供应链批次"
          rowKey={(b) => `${b.kind}-${b.date}-${b.note}-${b.qty}`}
          rows={batches}
          rowClassName={(b) => (b.overdue ? "pmc-overview__row-hl" : "")}
          columns={[
            { title: "状态", key: "kind", width: 120, render: (_, b) => <Tag bordered={false}>{KIND[b.kind] ?? b.kind}</Tag> },
            { title: "件数", key: "qty", width: 80, align: "right", render: (_, b) => fmt(b.qty) },
            { title: "预计可售日", key: "date", width: 110, render: (_, b) => (b.date === today ? "现在（收货中）" : b.date || "—") },
            {
              title: "说明", key: "note",
              render: (_, b) => (
                <Space size={4} wrap>
                  {b.store && r.stores.length > 1 ? <Muted>【{b.store}】</Muted> : null}
                  <span>{b.note}</span>
                  {b.overdue && <StatusTagCell label="已过可售日" color="error" />}
                  {b.inspected && <StatusTagCell label="查验" color="warning" />}
                </Space>
              ),
            },
          ]}
        />
        {r.dom_rows.length > 0 && (
          <>
            <h4>国内仓批次在仓天数（惠州）</h4>
            <OverviewDetailTable<DomRow>
              label="国内仓批次"
              rowKey="batch"
              rows={r.dom_rows as DomRow[]}
              rowClassName={(b) => (b.age > domesticDays ? "pmc-overview__row-hl" : "")}
              columns={[
                { title: "批次", key: "batch", render: (_, b) => <span className="pmc-overview__mono">{b.batch}</span> },
                { title: "入库日", key: "in_date", render: (_, b) => b.in_date },
                { title: "在仓天数", key: "age", align: "right", render: (_, b) => <span className={b.age > domesticDays ? "pmc-overview__warn" : undefined}>{b.age} 天</span> },
                { title: "余额件数", key: "qty", align: "right", render: (_, b) => fmt(b.qty) },
              ]}
            />
          </>
        )}
        <h4>异常与提示</h4>
        {r.issues.length === 0 ? <Muted>无异常</Muted> : r.issues.map((i) => (
          <div key={i.label} className="pmc-overview__note"><StatusTagCell label={i.label} color={i.level} /><span>{i.detail}</span></div>
        ))}
        <h4>补货</h4>
        <div className="pmc-overview__formula">
          <div>建议量 = 日销 {fmt1(r.daily)} ×（提前期 {fmt1(r.lead_total)} + 补货周期 {r.cycle_days ?? "—"}{p.safety ? ` + 安全 ${p.safety}` : ""}）− 有效供应 {fmt(r.supply)} = <b>{fmt(r.suggest)}</b> 件</div>
          {r.overseas_alloc > 0 && <div>扣海外仓 <b>{fmt(r.overseas_alloc)}</b> 件（同 SKU 海外仓共 {fmt(r.overseas_total)} 件，断货最早的 ItemID 先用；海外仓 → WFS 人工处理）</div>}
          {r.suggest > 0 && <div>国内采购 = {fmt(r.purchase)} 件{r.boxed ? ` → 按默认箱规 ${r.box} 件/箱取整 = ${fmt(r.boxed)} 件` : ""}{r.purchase < (p.minQty ?? 50) ? `（< ${p.minQty ?? 50} 件不出草稿）` : ""}</div>}
          <div>{r.is_draft && <Tag bordered={false} className="pmc-overview__mono">{r.draft_id}</Tag>}<b>{r.draft_text}</b>{r.is_draft && <Muted> · 草稿以「自动补货」页为准（本页只读）</Muted>}</div>
        </div>
        <h4>运营日志</h4>
        <Alert type="info" showIcon message="运营日志模块未建，后续讨论；上线后这里显示该 ItemID 的运营判断、处理与跟进记录。" />
      </div>
    </Drawer>
  );
}

export default OverviewItemDrawer;

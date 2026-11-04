/** 口径说明 drawer: unattributed quantities, overseas stock and data-scope notes. */
import { Descriptions, Drawer } from "antd";
import { fmt, KIND } from "@/pages/pmc/overview/overviewDisplay";
import type { OverviewSummary } from "@/pages/pmc/overview/overviewTypes";

interface OverviewFootnoteProps {
  open: boolean;
  summary?: OverviewSummary;
  onClose: () => void;
}

function OverviewFootnote({ open, summary: s, onClose }: OverviewFootnoteProps) {
  const byKind = Object.fromEntries((s?.unattributed ?? []).map((x) => [x.kind, x.qty]));
  return (
    <Drawer open={open} title="口径说明" width="min(640px, calc(100vw - 24px))" onClose={onClose}>
      <Descriptions
        size="small"
        bordered
        column={1}
        items={[
          { key: "date", label: "数据日", children: s ? `${s.data_date}（8088 数据日快照，过渡，每周刷新）` : "—" },
          { key: "source", label: "数据来源", children: s?.source_note ?? "—" },
          {
            key: "unattributed", label: "未归属到 ItemID（不计入任何一行）",
            children: s ? `采购计划 ${fmt(byKind.plan ?? 0)} · 采购单待到货 ${fmt(byKind.po ?? 0)} · 待下单 ${fmt(byKind.po_pending ?? 0)} · 国内仓 ${fmt(byKind.domestic ?? 0)} · 已发货货件 ${fmt(byKind.shipped ?? 0)} 件（原因：${s.unattributed.map((x) => `${KIND[x.kind] ?? x.kind} ${fmt(x.qty)} 件 ${x.why}`).join("；")}）` : "—",
          },
          { key: "overseas", label: "海外仓", children: s ? `不计入全流程库存，按 SKU 单独统计：${fmt(s.overseas_total)} 件；本轮可先补 WFS 的 ItemID ${fmt(s.kpi.overseas)} 个。` : "—" },
          { key: "scope", label: "口径", children: "主表各段 = 自动补货互斥口径（可相加、不含海外仓）；下载的「店铺 × SKU 明细」= 运营数据表分段口径（可重叠、不要跨段相加）。" },
          { key: "todo", label: "未接入", children: "Walmart 数据列（购物车 / 价格 / 质量分等，需 Walmart 报表接入另行审批）；归档；草稿审批状态；运营日志。本页只读，不调用领星 / Walmart。" },
        ]}
      />
    </Drawer>
  );
}

export default OverviewFootnote;

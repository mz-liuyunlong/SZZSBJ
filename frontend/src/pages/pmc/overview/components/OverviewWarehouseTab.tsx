/** 仓库分布 tab: domestic / overseas warehouses with stock (read-only). */
import { Alert, Tag, Typography } from "antd";
import OverviewDetailTable from "@/pages/pmc/overview/components/OverviewDetailTable";
import { overviewErrorText } from "@/pages/pmc/overview/overviewApi";
import { fmt } from "@/pages/pmc/overview/overviewDisplay";
import { useOverviewWarehousesQuery } from "@/pages/pmc/overview/overviewQueries";
import type { OverviewWarehouse } from "@/pages/pmc/overview/overviewTypes";

type Row = OverviewWarehouse & Record<string, unknown>;

function OverviewWarehouseTab() {
  const query = useOverviewWarehousesQuery(true);
  if (query.error) return <Alert type="error" showIcon message={overviewErrorText(query.error)} />;
  const data = query.data;
  return (
    <div className="pmc-overview__tab-body">
      <Typography.Text type="secondary">领星仓库库存明细（全量）；只列国内仓 / 海外仓且有库存的仓；在仓天数按批次入库日</Typography.Text>
      <OverviewDetailTable<Row>
        label="仓库分布"
        rowKey="name"
        loading={query.isPending}
        rows={(data?.warehouses ?? []) as Row[]}
        emptyText="当前没有有库存的国内仓 / 海外仓"
        columns={[
          { title: "仓库", key: "name", render: (_, w) => w.name },
          { title: "分类", key: "class", render: (_, w) => <Tag bordered={false}>{w.warehouse_class}</Tag> },
          { title: "可用", key: "valid", align: "right", render: (_, w) => fmt(w.valid) },
          { title: "锁定", key: "lock", align: "right", render: (_, w) => fmt(w.lock) },
          { title: "在库合计", key: "total", align: "right", render: (_, w) => fmt(w.total) },
          { title: "调拨在途", key: "onway", align: "right", render: (_, w) => fmt(w.onway) },
          { title: "有库存 SKU", key: "skus", align: "right", render: (_, w) => fmt(w.skus) },
          { title: "在仓天数 平均 / 最长", key: "age", render: (_, w) => (w.age_avg !== null ? `${w.age_avg} / ${w.age_max} 天` : "—") },
          { title: "在仓天数分布", key: "bands", render: (_, w) => (Object.keys(w.age_bands).length ? Object.entries(w.age_bands).map(([k, v]) => `${k} ${fmt(v)}`).join(" · ") : "—") },
        ]}
      />
      {data && <Alert type="warning" showIcon message={`海外仓 ${fmt(data.overseas_total)} 件不计入 ItemID 主表与覆盖天数。`} />}
    </div>
  );
}

export default OverviewWarehouseTab;

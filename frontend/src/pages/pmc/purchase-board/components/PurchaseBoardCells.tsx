/** Purchase-board cell components shared by the table and the detail Modal. */
import { Tag, Tooltip, Typography } from "antd";
import { WalmartItemLink } from "@/components/report-table/cells";
import StatusTag from "@/shared/status/StatusTag";
import {
  exclusionLabels,
  itemIdSourceLabels,
  skuCycleSourceLabels,
  stageLabels,
} from "@/pages/pmc/purchase-board/purchaseBoardDisplay";
import type {
  PurchaseBoardRow,
  PurchaseStageRef,
  SkuCycleBrief,
  SkuCycleSample,
} from "@/pages/pmc/purchase-board/purchaseBoardTypes";

/** Status column: stage tag + overdue days (purchase vs arrival kept apart) + WFS flag. */
export function StageCell({ stage, wfsNotReady }: { stage: PurchaseStageRef; wfsNotReady?: boolean | null }) {
  const preset = stageLabels[stage.stageCode] ?? stageLabels.UNKNOWN;
  const overdue = stage.overdueDays > 0
    ? (
      <Tooltip title={stage.overdueKind === "purchase" ? "待采购超时" : "到货逾期"}>
        <Tag color="red">
          {stage.overdueKind === "purchase" ? "待采购超时" : "逾期"} {stage.overdueDays} 天
        </Tag>
      </Tooltip>
    )
    : null;
  return (
    <span className="purchase-board__stage-cell">
      <StatusTag value={stage.stageCode} label={preset.label} color={preset.color} />
      {overdue}
      {wfsNotReady ? <Tag color="orange">WFS 待转换</Tag> : null}
    </span>
  );
}

export function SkuCycleSamplesTooltip({ samples }: { samples: SkuCycleSample[] }) {
  if (samples.length === 0) return <span>暂无到货样本</span>;
  return (
    <table className="purchase-board__samples">
      <thead>
        <tr><th>采购单号</th><th>下单</th><th>到仓</th><th>天数</th><th>剔除</th></tr>
      </thead>
      <tbody>
        {samples.slice(0, 5).map((sample) => (
          <tr key={sample.purchaseOrderSn} className={sample.used ? undefined : "is-excluded"}>
            <td>{sample.purchaseOrderSn}</td>
            <td>{sample.orderDate}</td>
            <td>{sample.arrivalDate}</td>
            <td>{sample.cycleDays}</td>
            <td>{sample.exclusion ? exclusionLabels[sample.exclusion] : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** SKU-level actual cycle brief; samples are loaded lazily by the caller (detail Modal). */
export function SkuCycleBriefCell({ cycle }: { cycle: SkuCycleBrief }) {
  if (cycle.valueDays === null) {
    return (
      <Typography.Text type="secondary">
        {cycle.source ? skuCycleSourceLabels[cycle.source] : "—"}
      </Typography.Text>
    );
  }
  return (
    <span className="purchase-board__cycle-cell">
      <span>{cycle.valueDays.toFixed(1)} 天</span>
      {cycle.sampleCount !== null && cycle.sampleCount > 0 && (
        <Typography.Text type="secondary">（{cycle.sampleCount} 样本）</Typography.Text>
      )}
      {cycle.unstable && <Tag color="orange">不稳定</Tag>}
    </span>
  );
}

export function ItemIdCell({ row }: { row: PurchaseBoardRow }) {
  const { itemId } = row;
  if (!itemId.itemId) {
    return (
      <Tag color={itemId.matchStatus === "unresolved" ? "red" : "gold"}>
        {itemIdSourceLabels[itemId.source]}
      </Tag>
    );
  }
  return (
    <span className="purchase-board__itemid-cell">
      <WalmartItemLink itemId={itemId.itemId} />
      <Typography.Text type="secondary">{itemIdSourceLabels[itemId.source]}</Typography.Text>
    </span>
  );
}


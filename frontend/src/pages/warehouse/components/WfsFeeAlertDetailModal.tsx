import { Button, Descriptions, Modal, Space, Tag, Timeline, Typography } from "antd";
import {
  formatWfsMoney,
  getPendingWfsAmount,
  type WfsFeeAlertCurrency,
  type WfsFeeAlertRow,
} from "@/pages/warehouse/wfsFeeAlertTypes";

interface WfsFeeAlertDetailModalProps {
  row?: WfsFeeAlertRow;
  currency: WfsFeeAlertCurrency;
  onClose: () => void;
  onOpenFollow: (row: WfsFeeAlertRow) => void;
}

const priorityColors = {
  高: "red",
  中: "orange",
  低: "default",
};

function WfsFeeAlertDetailModal({ row, currency, onClose, onOpenFollow }: WfsFeeAlertDetailModalProps) {
  if (!row) return null;

  return (
    <Modal
      width={860}
      open
      title="WFS费用异常详情"
      onCancel={onClose}
      footer={(
        <Space>
          <Button onClick={() => onOpenFollow(row)}>开Case</Button>
          <Button onClick={() => onOpenFollow(row)}>编辑跟进</Button>
          <Button type="primary" onClick={onClose}>关闭</Button>
        </Space>
      )}
      destroyOnHidden
    >
      <section className="wfs-fee-alert__detail" aria-label="WFS费用异常详情内容">
        <div className="wfs-fee-alert__detail-head">
          <div className="wfs-fee-alert__detail-image" aria-label={row.imageLabel}>{row.imageSymbol}</div>
          <div>
            <Typography.Title level={4}>{row.sku}</Typography.Title>
            <Typography.Text type="secondary">{row.productName} / {row.msku} / {row.productId}</Typography.Text>
            <div className="wfs-fee-alert__detail-tags">
              <Tag color={priorityColors[row.level]}>{row.level}优先级</Tag>
              <Tag color={row.caseNo ? "blue" : "orange"}>{row.status}</Tag>
              <Tag>{row.store}</Tag>
              <Tag>{row.owner}</Tag>
            </div>
          </div>
        </div>

        <Descriptions size="small" bordered column={3}>
          <Descriptions.Item label="已收WFS费用">{formatWfsMoney(row.chargedFee, currency)}</Descriptions.Item>
          <Descriptions.Item label="应收WFS费用">{formatWfsMoney(row.standardFee, currency)}</Descriptions.Item>
          <Descriptions.Item label="多收金额">{formatWfsMoney(row.overFee, currency)}</Descriptions.Item>
          <Descriptions.Item label="单件多收">{formatWfsMoney(row.unitOverFee, currency)}</Descriptions.Item>
          <Descriptions.Item label="已追回金额">{formatWfsMoney(row.recoveredAmount, currency)}</Descriptions.Item>
          <Descriptions.Item label="待追回金额">{formatWfsMoney(getPendingWfsAmount(row), currency)}</Descriptions.Item>
          <Descriptions.Item label="订单量">{row.orders.toLocaleString("zh-CN")}</Descriptions.Item>
          <Descriptions.Item label="销量">{row.units.toLocaleString("zh-CN")}</Descriptions.Item>
          <Descriptions.Item label="异常原因">{row.reason}</Descriptions.Item>
          <Descriptions.Item label="发现时间">{row.discoveredAt}</Descriptions.Item>
          <Descriptions.Item label="Case编号">{row.caseNo || "未开Case"}</Descriptions.Item>
          <Descriptions.Item label="下次跟进">{row.nextFollowAt}</Descriptions.Item>
        </Descriptions>

        <div className="wfs-fee-alert__detail-section">
          <Typography.Title level={5}>运营跟进</Typography.Title>
          <Timeline
            items={[
              { color: "blue", children: `发现异常：${row.discoveredAt}，原因：${row.reason}` },
              { color: row.caseNo ? "green" : "orange", children: row.caseNo ? `已开Case：${row.caseNo}` : "暂未开Case，需运营补充证据" },
              { color: "gray", children: row.latestFollow },
            ]}
          />
        </div>
      </section>
    </Modal>
  );
}

export default WfsFeeAlertDetailModal;

import { Button, Descriptions, Form, Input, Modal, Space, Tag, Timeline, Typography } from "antd";
import { useState } from "react";
import {
  formatWfsMoney,
  getPendingWfsAmount,
  type WfsFeeAlertCurrency,
  type WfsFeeAlertFollowFormValues,
  type WfsFeeAlertRow,
} from "@/pages/warehouse/wfsFeeAlertTypes";

interface WfsFeeAlertDetailModalProps {
  row?: WfsFeeAlertRow;
  currency: WfsFeeAlertCurrency;
  onClose: () => void;
  onSubmit: (values: WfsFeeAlertFollowFormValues) => Promise<void>;
  onOpenAbandon: (row: WfsFeeAlertRow) => void;
  canFollow: boolean;
  canArchiveRequest: boolean;
}


interface FollowInput {
  caseNo?: string;
  latestFollow: string;
}

function FollowEditor({
  row,
  onSubmit,
}: {
  row: WfsFeeAlertRow;
  onSubmit: (values: WfsFeeAlertFollowFormValues) => Promise<void>;
}) {
  const [form] = Form.useForm<FollowInput>();
  const [saving, setSaving] = useState(false);

  const submit = async (values: FollowInput) => {
    if (saving) return;
    setSaving(true);
    try {
      await onSubmit({
        status: row.status,
        caseNo: values.caseNo?.trim() ?? "",
        recoveredAmount: row.recoveredAmount,
        latestFollow: values.latestFollow.trim(),
      });
      form.resetFields(["latestFollow"]);
    } catch {
      // 保留用户输入，错误提示由调用页面负责。
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="wfs-fee-alert__detail-section">
      <Typography.Title level={5}>新增跟进</Typography.Title>
      <Typography.Paragraph type="secondary">
        已登记 {row.followCount ?? 0} 次跟进。
        每次成功保存自动编号、记录时间和操作人；下次跟进自动安排在7天后。历史内容不可编辑或删除。
      </Typography.Paragraph>
      <Form<FollowInput>
        form={form}
        layout="vertical"
        initialValues={{
          caseNo: row.caseNo,
          latestFollow: "",
        }}
        onFinish={(values) => void submit(values)}
      >
        <Form.Item label="Case编号" name="caseNo">
          <Input />
        </Form.Item>
        <Form.Item
          label="本次跟进内容"
          name="latestFollow"
          rules={[{
            required: true,
            whitespace: true,
            message: "请输入跟进内容",
          }]}
        >
          <Input.TextArea
            rows={3}
            maxLength={4000}
            showCount
            placeholder="保存后不可修改或删除"
          />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={saving}>
          保存本次跟进
        </Button>
      </Form>
    </section>
  );
}

const priorityColors = {
  高: "red",
  中: "orange",
  低: "default",
};

function WfsFeeAlertDetailModal({
  row,
  currency,
  onClose,
  onSubmit,
  onOpenAbandon,
  canFollow,
  canArchiveRequest,
}: WfsFeeAlertDetailModalProps) {
  if (!row) return null;

  return (
    <Modal
      width={1020}
      className="wfs-fee-alert__compact-modal"
      style={{ top: 16 }}
      styles={{
        body: {
          maxHeight: "calc(100dvh - 180px)",
          overflowY: "auto",
        },
      }}
      open
      title="WFS费用异常详情"
      onCancel={onClose}
      footer={(
        <Space>
          {canArchiveRequest && <Button danger disabled={row.status !== "未开Case" && row.status !== "跟进中"} onClick={() => onOpenAbandon(row)}>申请放弃跟进</Button>}
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
          <div className="wfs-fee-alert__timeline-scroll">
            <Timeline
              items={[
                ...((row.followLog ?? "")
                  .split(/\r?\n/)
                  .map((value) => value.trim())
                  .filter(Boolean)
                  .reverse()
                  .map((value, index) => ({
                    color: index === 0 ? "blue" : "gray",
                    children: value,
                  }))),
                {
                  color: row.caseNo ? "green" : "orange",
                  children: row.caseNo
                    ? `已开Case：${row.caseNo}`
                    : "暂未开Case，需运营补充证据",
                },
                {
                  color: "blue",
                  children: `发现异常：${row.discoveredAt}，原因：${row.reason}`,
                },
              ]}
            />
          </div>
        </div>
        {canFollow && (row.status === "未开Case" || row.status === "跟进中") && (
          <FollowEditor key={row.id} row={row} onSubmit={onSubmit} />
        )}
      </section>
    </Modal>
  );
}

export default WfsFeeAlertDetailModal;

import { Button, DatePicker, Form, Input, InputNumber, Modal, Select, Space, Typography } from "antd";
import dayjs from "dayjs";
import { useEffect } from "react";
import {
  formatWfsMoney,
  getPendingWfsAmount,
  type WfsFeeAlertCaseStatus,
  type WfsFeeAlertCurrency,
  type WfsFeeAlertFollowFormValues,
  type WfsFeeAlertRow,
} from "@/pages/warehouse/wfsFeeAlertTypes";

interface WfsFeeAlertFollowModalProps {
  row?: WfsFeeAlertRow;
  currency: WfsFeeAlertCurrency;
  onClose: () => void;
  onSubmit: (values: WfsFeeAlertFollowFormValues) => void;
}

interface FollowFormValues {
  status: WfsFeeAlertCaseStatus;
  caseNo?: string;
  recoveredAmount?: number;
  nextFollowAt?: dayjs.Dayjs;
  latestFollow?: string;
}

const statusOptions: { label: WfsFeeAlertCaseStatus; value: WfsFeeAlertCaseStatus }[] = [
  { label: "未开Case", value: "未开Case" },
  { label: "已开Case", value: "已开Case" },
  { label: "跟进中", value: "跟进中" },
  { label: "已追回", value: "已追回" },
  { label: "驳回", value: "驳回" },
  { label: "已关闭", value: "已关闭" },
];

function WfsFeeAlertFollowModal({
  row,
  currency,
  onClose,
  onSubmit,
}: WfsFeeAlertFollowModalProps) {
  const [form] = Form.useForm<FollowFormValues>();

  useEffect(() => {
    if (!row) return;

    form.setFieldsValue({
      status: row.status,
      caseNo: row.caseNo,
      recoveredAmount: row.recoveredAmount,
      nextFollowAt: row.nextFollowAt && row.nextFollowAt !== "-" ? dayjs(row.nextFollowAt) : undefined,
      latestFollow: row.latestFollow,
    });
  }, [form, row]);

  if (!row) return null;

  return (
    <Modal
      width={720}
      open
      title="编辑跟进信息"
      className="wfs-fee-alert-follow-modal"
      onCancel={onClose}
      destroyOnHidden
      footer={null}
    >
      <div className="wfs-fee-alert-follow-modal__summary">
        <div>
          <Typography.Text type="secondary">SKU</Typography.Text>
          <strong>{row.sku}</strong>
        </div>
        <div>
          <Typography.Text type="secondary">多收金额</Typography.Text>
          <strong className="wfs-fee-alert-follow-modal__danger">
            {formatWfsMoney(row.overFee, currency)}
          </strong>
        </div>
        <div>
          <Typography.Text type="secondary">待追回</Typography.Text>
          <strong>{formatWfsMoney(getPendingWfsAmount(row), currency)}</strong>
        </div>
      </div>

      <Form<FollowFormValues>
        form={form}
        layout="vertical"
        onFinish={(values) => {
          onSubmit({
            status: values.status,
            caseNo: values.caseNo?.trim() ?? "",
            recoveredAmount: values.recoveredAmount ?? 0,
            nextFollowAt: values.nextFollowAt?.format("YYYY-MM-DD") ?? "-",
            latestFollow: values.latestFollow?.trim() ?? "",
          });
        }}
      >
        <div className="wfs-fee-alert-follow-modal__grid">
          <Form.Item
            label="Case状态"
            name="status"
            rules={[{ required: true, message: "请选择Case状态" }]}
          >
            <Select options={statusOptions} />
          </Form.Item>

          <Form.Item label="Case编号" name="caseNo">
            <Input placeholder="例如 CS-20260913-001" />
          </Form.Item>

          <Form.Item label="已追回金额" name="recoveredAmount">
            <InputNumber
              min={0}
              precision={2}
              addonBefore={currency === "CNY" ? "¥" : "$"}
              style={{ width: "100%" }}
            />
          </Form.Item>

          <Form.Item label="下次跟进时间" name="nextFollowAt">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </div>

        <Form.Item
          label="最新跟进记录"
          name="latestFollow"
          rules={[{ required: true, message: "请填写最新跟进记录" }]}
        >
          <Input.TextArea
            rows={4}
            placeholder="例如：已提交尺寸重量截图，等待平台复核；预计明日再次跟进。"
          />
        </Form.Item>

        <div className="wfs-fee-alert-follow-modal__footer">
          <Space>
            <Button onClick={onClose}>取消</Button>
            <Button type="primary" htmlType="submit">保存跟进</Button>
          </Space>
        </div>
      </Form>
    </Modal>
  );
}

export default WfsFeeAlertFollowModal;

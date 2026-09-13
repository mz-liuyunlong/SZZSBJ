import { Button, Form, Input, Modal } from "antd";
import { useEffect } from "react";
import {
  type OperationLogLinkFormValues,
  type OperationLogRow,
} from "@/pages/operations/operationLogTypes";

interface OperationLogLinkEditorModalProps {
  row?: OperationLogRow;
  entryType?: "keyword" | "ad";
  onClose: () => void;
  onKeepMissing: (row: OperationLogRow, entryType: "keyword" | "ad") => void;
  onSave: (row: OperationLogRow, entryType: "keyword" | "ad", values: OperationLogLinkFormValues) => void;
}

function OperationLogLinkEditorModal({
  row,
  entryType,
  onClose,
  onKeepMissing,
  onSave,
}: OperationLogLinkEditorModalProps) {
  const [form] = Form.useForm<OperationLogLinkFormValues>();

  useEffect(() => {
    if (!row || !entryType) return;

    const entryName = entryType === "keyword" ? "关键词" : "广告";
    form.setFieldsValue({
      entryType,
      entryName: `${entryName} - ${row.productId}`,
      entryUrl: `/${entryType === "keyword" ? "keywords" : "ads"}/${row.productId}`,
      note: "",
    });
  }, [entryType, form, row]);

  if (!row || !entryType) return null;

  const label = entryType === "keyword" ? "关键词" : "广告";

  return (
    <Modal
      width={600}
      open
      title={`补录${label}快捷入口`}
      className="operation-log-link-modal"
      onCancel={onClose}
      destroyOnHidden
      footer={null}
    >
      <div className="operation-log-link-modal__summary">
        <strong>{row.productId} · {row.productName}</strong>
        <span>{row.sku} / {row.store} / {row.owner}</span>
      </div>
      <div className="operation-log-link-modal__tip">
        当前{label}页面缺失。保存后，表格里的「{entryType === "keyword" ? "词" : "广"}」入口会从红色缺失状态变为可打开状态，方便运营后续快速调整。
      </div>
      <Form<OperationLogLinkFormValues>
        form={form}
        layout="vertical"
        onFinish={(values) => onSave(row, entryType, values)}
      >
        <Form.Item label="页面名称" name="entryName" rules={[{ required: true, message: "请填写页面名称" }]}>
          <Input />
        </Form.Item>
        <Form.Item label="页面地址" name="entryUrl" rules={[{ required: true, message: "请填写页面地址" }]}>
          <Input placeholder="可填写系统内部路由或外部后台地址" />
        </Form.Item>
        <Form.Item label="备注" name="note">
          <Input.TextArea rows={4} placeholder={`例如：该商品ID尚未建立${label}页面，先补录入口再继续运营日志。`} />
        </Form.Item>
        <div className="operation-log-link-modal__footer">
          <Button onClick={() => onKeepMissing(row, entryType)}>仍标记缺失</Button>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" htmlType="submit">保存并启用</Button>
        </div>
      </Form>
    </Modal>
  );
}

export default OperationLogLinkEditorModal;

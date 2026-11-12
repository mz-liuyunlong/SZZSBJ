/** 表格上方的核对提示条：和领星账单对不上的 店铺 × 账单期 × 费用类型；财务核实后标「已核实」（必填原因）。 */
import { Alert, Button, Input, Modal, Space, Table, Tag, Typography, message } from "antd";
import { useState } from "react";
import { FinMoney } from "@/pages/finance/FinanceBoardFrame";
import { CHECK_TEXT, isForbidden, num, useChecks, verifyCheck, wfsErrorText, type ApiCheck } from "./wfsFeesApi";

function ChecksBar({ storeId, reportKey, storeCode, typeName, onChanged }: {
  storeId?: string; reportKey?: string; storeCode: Map<string, string>; typeName: Map<string, string>; onChanged: () => void;
}) {
  const checks = useChecks({ store_id: storeId, report_key: reportKey });
  const [open, setOpen] = useState(false);
  const [verifying, setVerifying] = useState<ApiCheck>();
  const [reason, setReason] = useState("");
  const [messageApi, messageHolder] = message.useMessage();
  const items = checks.data ?? [];
  if (checks.error && isForbidden(checks.error)) return null;
  if (!items.length) return null;
  const submit = async () => {
    if (!verifying) return;
    try {
      await verifyCheck(verifying, reason);
      void messageApi.success("已标为已核实");
      setVerifying(undefined); setReason("");
      void checks.refetch(); onChanged();
    } catch (error) {
      void messageApi.error(wfsErrorText(error));
    }
  };
  return (
    <>
      {messageHolder}
      <Alert type="warning" showIcon className="fin-wfs__checks" message={<span>和领星账单对不上的有 <b>{items.length}</b> 组（店铺 × 账单期 × 费用类型）<Button type="link" size="small" onClick={() => setOpen((v) => !v)}>{open ? "收起" : "展开"}</Button></span>}
        description={open && (
          <Table<ApiCheck> size="small" bordered pagination={false} rowKey={(c) => `${c.store_id}|${c.report_key}|${c.fee_type}`} dataSource={items} columns={[
            { title: "店铺", width: 80, render: (_, c) => storeCode.get(c.store_id) ?? c.store_id },
            { title: "账单日", dataIndex: "report_date", width: 100 },
            { title: "费用类型", width: 180, render: (_, c) => `${typeName.get(c.fee_type) ?? c.fee_type} ${c.fee_type}` },
            { title: "领星", width: 110, align: "right", render: (_, c) => <FinMoney value={num(c.lingxing_amount)} cur="USD" /> },
            { title: "报表", width: 110, align: "right", render: (_, c) => <FinMoney value={num(c.report_amount)} cur="USD" /> },
            { title: "差", width: 100, align: "right", render: (_, c) => <FinMoney value={(num(c.lingxing_amount) ?? 0) - (num(c.report_amount) ?? 0)} cur="USD" /> },
            { title: "状态", width: 90, render: (_, c) => <Tag color={c.status === "ok" ? "green" : "red"} bordered={false}>{CHECK_TEXT[c.status]}</Tag> },
            { title: "操作", width: 90, render: (_, c) => <Button type="link" size="small" onClick={() => setVerifying(c)}>已核实</Button> },
          ]} />
        )} />
      <Modal open={Boolean(verifying)} title="标为已核实" okText="确定" cancelText="取消" okButtonProps={{ disabled: !reason.trim() }} onOk={() => void submit()} onCancel={() => { setVerifying(undefined); setReason(""); }} destroyOnHidden>
        {verifying && <Space direction="vertical" style={{ width: "100%" }}>
          <Typography.Text type="secondary">{storeCode.get(verifying.store_id) ?? verifying.store_id} · {verifying.report_date} · {typeName.get(verifying.fee_type) ?? verifying.fee_type}：领星 {verifying.lingxing_amount ?? "—"}，报表 {verifying.report_amount ?? "—"}</Typography.Text>
          <Input.TextArea autoFocus rows={3} maxLength={500} showCount placeholder="必填：核实结果（比如：报表漏一行，已向 Walmart 核实 / 期末一天时区差，下一期多出同样的数）" value={reason} onChange={(e) => setReason(e.target.value)} />
        </Space>}
      </Modal>
    </>
  );
}

export default ChecksBar;

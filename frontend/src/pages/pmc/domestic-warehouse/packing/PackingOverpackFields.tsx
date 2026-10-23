/** Explicit extra-stock confirmation and mandatory shortage reason are separate outcomes. */
import { Alert, Checkbox, Form, Input } from "antd";
export default function PackingOverpackFields({ excess, available, rebox }: { excess: number; available?: number | null; rebox: boolean }) {
  if (excess <= 0) return null;
  if (available === undefined || available === null) return <Alert type="warning" message="库存证据不足，暂不能放行多装" />;
  if (excess <= available) return <>
    <Alert type="warning" message={`超出 ${excess} 件，占用同 SKU 其他在仓库存`} description={`同账号、同仓库全部入库单可额外占用 ${available} 件，已经扣除当前 PK 的审批数量和其他有效占用。`} />
    <Form.Item name="confirm_extra" valuePropName="checked" rules={[{ validator: (_, value) => value === true ? Promise.resolve() : Promise.reject(new Error("请确认占用额外库存")) }]}><Checkbox>确认占用额外库存</Checkbox></Form.Item>
  </>;
  return <>
    <Alert type="warning" message={`超出 ${excess} 件，可用余量 ${available} 件，缺口 ${excess - available} 件`} description={rebox ? "将记录补入库任务和改装箱提议，实际装箱保持原记录；补齐后需再次提交改装箱。" : "不能完成；填写原因后记录待补入库单和本地待通知任务。"} />
    {!rebox && <Form.Item name="reason" label="超发原因" rules={[{ required: true, whitespace: true, min: 2, max: 500 }]}><Input.TextArea rows={2} maxLength={500} /></Form.Item>}
  </>;
}

/** Draft carton rows are editable until completion; totals are rechecked by the backend. */
import { Alert, Button, Checkbox, Col, Form, Input, InputNumber, Row, Select, Space, Typography, type FormInstance } from "antd";
import PackingPackageFields from "./PackingPackageFields";
import type { BoxInput, PackingWarehouseRow } from "./packingWarehouseTypes";
interface Props { row: PackingWarehouseRow; form: FormInstance; hideReason?: boolean }
export default function PackingWarehouseBoxForm({ row, form, hideReason }: Props) {
  const lines = Form.useWatch("lines", form) as BoxInput[] | undefined;
  const measure = Form.useWatch("measure_package", form) as boolean | undefined;
  const total = (lines ?? []).reduce((n, line) => n + Number(line.boxes ?? 0) * Number(line.units_per_box ?? 0), 0);
  return <>
    <Alert type={total > row.approved_quantity ? "error" : "info"} showIcon message={`审批 ${row.approved_quantity} 件 · 当前装箱 ${total} 件`} description="支持暂存实际装箱；少装在完成时选择原因，超量在完成时校验同 SKU 库存。固定箱型：A 58×40×45，B 46×46×52，C 53×43×48 cm。" />
    <Form.List name="lines" rules={[{ validator: async (_, values) => { if (!values?.length || values.length > 20) throw new Error("需填写1至20行装箱"); } }]}>{(fields, { add, remove }, { errors }) => <>
      {fields.map(({ key, name, ...rest }) => <div className="domestic-packing__box-line" key={key}><Row gutter={10}>
        <Col span={6}><Form.Item {...rest} name={[name, "box_type"]} label={`第${name + 1}行箱型`} rules={[{ required: true }]}><Select options={[{ value: "A", label: "A 箱" }, { value: "B", label: "B 箱" }, { value: "C", label: "C 箱" }, { value: "custom", label: "自定义" }]} /></Form.Item></Col>
        <Col span={5}><Form.Item {...rest} name={[name, "boxes"]} label="箱数" rules={[{ required: true }, { type: "integer", min: 1, max: 9999 }]}><InputNumber min={1} max={9999} precision={0} className="domestic-packing__input" /></Form.Item></Col>
        <Col span={6}><Form.Item {...rest} name={[name, "units_per_box"]} label="每箱件数" rules={[{ required: true }, { type: "integer", min: 1, max: 100000 }]}><InputNumber min={1} max={100000} precision={0} className="domestic-packing__input" /></Form.Item></Col>
        <Col span={7}><Form.Item {...rest} name={[name, "gross_weight_kg"]} label="单箱毛重（kg）" rules={[{ required: true }]}><InputNumber min={0.01} max={200} precision={4} className="domestic-packing__input" /></Form.Item></Col>
      </Row>
      {lines?.[name]?.box_type === "custom" && <Row gutter={10}>{[{ key: "length_cm", label: "箱长（cm）" }, { key: "width_cm", label: "箱宽（cm）" }, { key: "height_cm", label: "箱高（cm）" }].map((field) => <Col span={8} key={field.key}><Form.Item name={[name, field.key]} label={field.label} rules={[{ required: true }]}><InputNumber min={1} max={300} precision={4} className="domestic-packing__input" /></Form.Item></Col>)}</Row>}
      <Button size="small" danger disabled={fields.length === 1} onClick={() => remove(name)}>删除第{name + 1}行</Button></div>)}
      <Space><Button disabled={fields.length >= 20} onClick={() => add({ box_type: "A", boxes: 1 })}>添加箱行</Button><Typography.Text type="secondary">最多20行；尾箱单独填写</Typography.Text></Space><Form.ErrorList errors={errors} />
    </>}</Form.List>
    {!hideReason && <Form.Item name="reason" label="数量差异原因" rules={[{ required: false, whitespace: true, max: 500 }]}><Input.TextArea rows={2} maxLength={500} placeholder="暂存备注（选填）；正式少装原因在打包完成时选择" /></Form.Item>}
    <Form.Item name="measure_package" valuePropName="checked"><Checkbox>补填本单单品包装尺寸和毛重（不修改产品资料）</Checkbox></Form.Item>
    {measure && <PackingPackageFields />}
  </>;
}

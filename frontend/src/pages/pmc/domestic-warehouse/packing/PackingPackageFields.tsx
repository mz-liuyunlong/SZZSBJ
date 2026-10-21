/** Warehouse measurements use cm/g, distinct from carton cm/kg. */
import { Col, Form, InputNumber, Row } from "antd";
export default function PackingPackageFields() {
  return <Row gutter={12}>{[{ key: "length_cm", label: "单品包装长（cm）", min: 0.1, max: 500 }, { key: "width_cm", label: "单品包装宽（cm）", min: 0.1, max: 500 }, { key: "height_cm", label: "单品包装高（cm）", min: 0.1, max: 500 }, { key: "gross_weight_g", label: "单品毛重（g）", min: 1, max: 100000 }].map((field) => <Col span={12} key={field.key}><Form.Item name={["package", field.key]} label={field.label} rules={[{ required: true, message: "请补填有效数值" }]}><InputNumber min={field.min} max={field.max} precision={4} className="domestic-packing__input" /></Form.Item></Col>)}</Row>;
}

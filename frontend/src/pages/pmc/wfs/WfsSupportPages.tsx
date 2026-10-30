/** WFS settings tab (local-only until settings PRP). */
import { Button, Card, Form, InputNumber, Space, message } from "antd";
import type { NavigationPage } from "@/config/navigation";
import WfsFrame from "./WfsFrame";

export function WfsSettingsPage({ page }: { page: NavigationPage }) {
  const [form] = Form.useForm();
  return (
    <WfsFrame page={page}>
      <Card title="看板阈值">
        <Form
          form={form}
          layout="vertical"
          initialValues={{ bufferDays: 10, arrivalFallbackDays: 10, qtyGap: 0 }}
          onFinish={() => message.success("只保存在当前页面，刷新后恢复")}
        >
          <Form.Item label="上架缓冲天数" name="bufferDays" extra="有 Receipt 时取最早 Receipt；没有则保持未知。">
            <InputNumber min={0} max={60} />
          </Form.Item>
          <Form.Item label="到仓后默认可售天数" name="arrivalFallbackDays" extra="正式规则未启用前，页面不用它推算可售日。">
            <InputNumber min={0} max={60} />
          </Form.Item>
          <Form.Item label="申报与实发允许差额" name="qtyGap">
            <InputNumber min={0} />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">保存到本页</Button>
            <Button onClick={() => form.resetFields()}>恢复示例</Button>
          </Space>
        </Form>
      </Card>
    </WfsFrame>
  );
}

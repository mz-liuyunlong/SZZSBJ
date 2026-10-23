/** Probe, create-board, exception and settings screens. All preview-only. */
import type { ProColumns } from "@ant-design/pro-components";
import { Button, Card, Form, InputNumber, Space, Typography, message } from "antd";
import type { NavigationPage } from "@/config/navigation";
import WfsFrame from "./WfsFrame";
import WfsTable from "./WfsTable";
import {
  createBoardRows,
  exceptionRows,
  probeRows,
  type CreateBoardRow,
  type ExceptionRow,
  type ProbeRow,
} from "./wfsMock";

export function ProbeListPage({ page }: { page: NavigationPage }) {
  const columns: ProColumns<ProbeRow>[] = [
    { title: "探测名称", dataIndex: "name" },
    { title: "店铺", dataIndex: "store" },
    { title: "GTIN", dataIndex: "gtin" },
    { title: "说明", dataIndex: "note" },
  ];
  return (
    <WfsFrame page={page} demo>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
        探测货件是演示流程。示例行不代表真实探测结果，也不会进入正式货件草稿。
      </Typography.Paragraph>
      <WfsTable label="探测货件表格" columns={columns} rows={probeRows} />
    </WfsFrame>
  );
}

export function CreateBoardPage({ page }: { page: NavigationPage }) {
  const columns: ProColumns<CreateBoardRow>[] = [
    { title: "示例草稿", dataIndex: "draft" },
    { title: "店铺", dataIndex: "store" },
    { title: "步骤", dataIndex: "step" },
    { title: "说明", dataIndex: "note" },
  ];
  return (
    <WfsFrame page={page} demo>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
        货件创建看板是演示流程。正式建货件走「待发货打包单」和「系统货件」。
      </Typography.Paragraph>
      <WfsTable label="货件创建看板表格" columns={columns} rows={createBoardRows} />
    </WfsFrame>
  );
}

export function ExceptionCenterPage({ page }: { page: NavigationPage }) {
  const columns: ProColumns<ExceptionRow>[] = [
    { title: "Shipment ID", dataIndex: "shipmentId" },
    { title: "店铺", dataIndex: "store" },
    { title: "类型", dataIndex: "kind" },
    { title: "说明", dataIndex: "detail" },
    { title: "操作", valueType: "option", render: () => <Button size="small" onClick={() => message.info("前端预览不会处理异常")}>标记已知</Button> },
  ];
  return (
    <WfsFrame page={page}>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
        测试货件不进入异常中心。下面两行只说明缺少签收和上架事实时页面如何展示，不是已经判定的异常结论。
      </Typography.Paragraph>
      <WfsTable label="异常中心表格" columns={columns} rows={exceptionRows} />
    </WfsFrame>
  );
}

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

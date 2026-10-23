/** Probe, create-board and exception lists, plus local settings. Frontend only. */
import { Button, Card, Form, InputNumber, Select, Space, message } from "antd";
import { useState } from "react";
import type { NavigationPage } from "@/config/navigation";
import WfsFrame from "./WfsFrame";
import WfsQueryPage from "./WfsQueryPage";

const storeFilter = (value: string | undefined, onChange: (value: string | undefined) => void) => (
  <Select allowClear showSearch aria-label="店铺" className="report-filter-select" placeholder="全部店铺" style={{ width: 220 }} value={value} onChange={onChange} options={[]} />
);

export function ProbeListPage({ page }: { page: NavigationPage }) {
  const [store, setStore] = useState<string>();
  const [probed, setProbed] = useState<string>();
  const [keyword, setKeyword] = useState("");
  return (
    <WfsQueryPage
      page={page}
      title="探测货件列表（0 条）"
      tableLabel="探测货件表格"
      emptyText="当前条件下暂无探测货件"
      searchAriaLabel="搜索探测货件"
      inputAriaLabel="搜索探测货件关键字"
      inputPlaceholder="草稿单 / 打包单"
      typeAriaLabel="探测货件搜索类型"
      typeOptions={[{ value: "id", label: "草稿单 / 打包单" }]}
      scrollX={1800}
      loadingLabel="正在加载探测货件，请稍候"
      keyword={keyword}
      onSearch={setKeyword}
      onReset={() => { setStore(undefined); setProbed(undefined); setKeyword(""); }}
      filters={(
        <>
          {storeFilter(store, setStore)}
          <Select
            allowClear
            aria-label="探测状态"
            className="report-filter-select"
            placeholder="探测状态"
            style={{ width: 140 }}
            value={probed}
            onChange={setProbed}
            options={[{ value: "y", label: "已探测" }, { value: "n", label: "未探测" }]}
          />
        </>
      )}
      columns={[
        { title: "草稿单", dataIndex: "draft", width: 160 },
        { title: "店铺", dataIndex: "store", width: 220 },
        { title: "来源票", dataIndex: "ticket", width: 160 },
        { title: "箱 / 件 / SKU / Item", dataIndex: "summary", width: 160 },
        { title: "货件类型", dataIndex: "type", width: 110 },
        { title: "探测地址", dataIndex: "address", width: 200 },
        { title: "探测结果", dataIndex: "result", width: 240 },
        { title: "探测次数", dataIndex: "count", width: 110 },
        { title: "天数", dataIndex: "age", width: 80 },
        { title: "备注", dataIndex: "remark", width: 140 },
        { title: "操作", dataIndex: "ops", width: 180 },
      ]}
    />
  );
}

export function CreateBoardPage({ page }: { page: NavigationPage }) {
  const [store, setStore] = useState<string>();
  const [mode, setMode] = useState<string>();
  const [status, setStatus] = useState("all");
  const [keyword, setKeyword] = useState("");
  return (
    <WfsQueryPage
      page={page}
      title="货件创建记录（0 条）"
      tableLabel="货件创建看板表格"
      emptyText="当前条件下暂无创建记录"
      searchAriaLabel="搜索货件创建看板"
      inputAriaLabel="搜索货件创建看板关键字"
      inputPlaceholder="创建单 / Shipment / 打包单"
      typeAriaLabel="货件创建看板搜索类型"
      typeOptions={[{ value: "id", label: "创建单 / Shipment / 打包单" }]}
      scrollX={2100}
      loadingLabel="正在加载货件创建看板，请稍候"
      keyword={keyword}
      onSearch={setKeyword}
      onReset={() => { setStore(undefined); setMode(undefined); setStatus("all"); setKeyword(""); }}
      filters={(
        <>
          {storeFilter(store, setStore)}
          <Select
            allowClear
            aria-label="创建方式"
            className="report-filter-select"
            placeholder="创建方式"
            style={{ width: 160 }}
            value={mode}
            onChange={setMode}
            options={[{ value: "direct", label: "直接创建" }, { value: "draft", label: "草稿探测后创建" }]}
          />
          <Select
            aria-label="创建结果"
            className="report-filter-select"
            style={{ width: 150 }}
            value={status}
            onChange={setStatus}
            options={[
              { value: "all", label: "全部" },
              { value: "submitting", label: "提交中" },
              { value: "created", label: "创建成功" },
              { value: "failed", label: "创建失败" },
              { value: "unknown", label: "结果确认中" },
            ]}
          />
        </>
      )}
      columns={[
        { title: "内部创建单", dataIndex: "draft", width: 160 },
        { title: "店铺", dataIndex: "store", width: 220 },
        { title: "创建方式", dataIndex: "mode", width: 140 },
        { title: "来源票", dataIndex: "ticket", width: 160 },
        { title: "箱 / 件 / SKU / Item", dataIndex: "summary", width: 160 },
        { title: "货件类型", dataIndex: "type", width: 110 },
        { title: "发货地址", dataIndex: "from", width: 180 },
        { title: "提交时间", dataIndex: "submittedAt", width: 140 },
        { title: "创建结果", dataIndex: "status", width: 120 },
        { title: "Walmart Shipment ID", dataIndex: "shipmentId", width: 180 },
        { title: "分配 / 失败原因", dataIndex: "result", width: 220 },
        { title: "领星同步情况", dataIndex: "sync", width: 140 },
        { title: "操作", dataIndex: "ops", width: 160 },
      ]}
    />
  );
}

export function ExceptionCenterPage({ page }: { page: NavigationPage }) {
  const [store, setStore] = useState<string>();
  const [kind, setKind] = useState<string>();
  const [status, setStatus] = useState<string>();
  const [owner, setOwner] = useState<string>();
  const [severity, setSeverity] = useState<string>();
  const [keyword, setKeyword] = useState("");
  return (
    <WfsQueryPage
      page={page}
      title="异常货件（0 个）"
      tableLabel="异常中心表格"
      emptyText="当前条件下暂无异常货件"
      searchAriaLabel="搜索异常中心"
      inputAriaLabel="搜索异常中心关键字"
      inputPlaceholder="货件号 / 情况 / 说明"
      typeAriaLabel="异常中心搜索类型"
      typeOptions={[{ value: "all", label: "货件号 / 说明" }]}
      scrollX={1680}
      loadingLabel="正在加载异常中心，请稍候"
      keyword={keyword}
      onSearch={setKeyword}
      onReset={() => { setStore(undefined); setKind(undefined); setStatus(undefined); setOwner(undefined); setSeverity(undefined); setKeyword(""); }}
      filters={(
        <>
          <Select
            allowClear
            aria-label="异常情况"
            className="report-filter-select"
            placeholder="全部情况"
            style={{ width: 200 }}
            value={kind}
            onChange={setKind}
            options={[
              { value: "unsigned", label: "预计到仓已过未签收" },
              { value: "forwarder", label: "货代已签收 · WFS未收货" },
              { value: "not-shelved", label: "签收满 10 天未上架" },
              { value: "receiving", label: "收货长期未完成" },
              { value: "short", label: "已关闭短少" },
            ]}
          />
          <Select
            allowClear
            aria-label="异常状态"
            className="report-filter-select"
            placeholder="异常状态"
            style={{ width: 130 }}
            value={status}
            onChange={setStatus}
            options={[
              { value: "open", label: "待处理" },
              { value: "doing", label: "处理中" },
              { value: "waiting", label: "等待沃尔玛" },
              { value: "resolved", label: "已解决" },
              { value: "closed", label: "已关闭" },
            ]}
          />
          {storeFilter(store, setStore)}
          <Select allowClear showSearch aria-label="产品负责人" className="report-filter-select" placeholder="产品负责人" style={{ width: 140 }} value={owner} onChange={setOwner} options={[]} />
          <Select
            allowClear
            aria-label="严重度"
            className="report-filter-select"
            placeholder="严重度"
            style={{ width: 110 }}
            value={severity}
            onChange={setSeverity}
            options={[{ value: "high", label: "高" }, { value: "mid", label: "中" }, { value: "low", label: "低" }]}
          />
        </>
      )}
      columns={[
        { title: "货件号", dataIndex: "code", width: 150 },
        { title: "异常情况", dataIndex: "kind", width: 220 },
        { title: "店铺", dataIndex: "store", width: 220 },
        { title: "Item ID / MSKU", dataIndex: "item", width: 160 },
        { title: "最早发现", dataIndex: "found", width: 120 },
        { title: "异常状态", dataIndex: "status", width: 110 },
        { title: "产品负责人", dataIndex: "owner", width: 120 },
        { title: "处理人", dataIndex: "handler", width: 100 },
        { title: "剩余处理时间", dataIndex: "remain", width: 130 },
        { title: "差异", dataIndex: "qty", width: 80 },
        { title: "异常说明", dataIndex: "detail", width: 280 },
      ]}
    />
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

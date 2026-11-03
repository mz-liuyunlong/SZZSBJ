/** WFS settings (PRP pmc-wfs-settings S2/S3): versioned rules, FC regions, creation defaults, channel dictionary. */
import { QuestionCircleOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Drawer, Form, Input, InputNumber, Modal, Radio, Select, Space, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import {
  REGIONS,
  SETTINGS_MANAGE_PERMISSION,
  createRuleVersion,
  getCreationDefaults,
  getRules,
  listFcRegions,
  listLogisticsChannels,
  listRuleVersions,
  listSettingsChanges,
  settingsError,
  updateCreationDefaults,
  updateFcRegion,
  type CreationDefaults,
  type FcRegion,
  type LogisticsChannel,
  type Region,
  type RuleRow,
  type SettingsChange,
} from "./settingsApi";

const SAMPLE_TAG = "示例 · 待定";
const today = () => new Date().toISOString().slice(0, 10);
const time = (v?: string | null) =>
  v ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Taipei", dateStyle: "short", timeStyle: "short" }).format(new Date(v)) : "—";
const entityLabel: Record<string, string> = { rules: "规则", fc_region: "仓库地区", creation_defaults: "创建默认值" };
const transportLabel: Record<CreationDefaults["transport"], string> = { LTL: "LTL 零担", SMALL_PARCEL: "小包裹", FTL: "FTL 整车" };

const newRow = (): RuleRow => ({
  rule_key: null, node: "", region: "全部", carrier: "全部", channel: "全部", days: 0, remind_days: 0,
  row_effective_date: today(), notify: "", remark: "", decided: false,
});

type Ask = { title: string; run: (reason: string, effective?: string) => Promise<unknown>; withDate?: boolean };

export default function WfsSettingsPage({ page, scope = "anonymous", permissions = [] }: { page: NavigationPage; scope?: string; permissions?: string[] }) {
  const qc = useQueryClient();
  const base = ["wfs-settings", scope];
  // Writes need the manage permission and a page that is no longer marked read-only in navigation (5173 stays greyed).
  const canManage = !page.readOnly && (permissions.includes("*") || permissions.includes(SETTINGS_MANAGE_PERMISSION));
  const writeHint = canManage ? undefined : page.readOnly ? "本页当前只读，写入待正式放行" : "没有 WFS 设置维护权限";

  const rules = useQuery({ queryKey: [...base, "rules"], queryFn: ({ signal }) => getRules(signal), retry: false });
  const versions = useQuery({ queryKey: [...base, "versions"], queryFn: ({ signal }) => listRuleVersions(signal), retry: false });
  const fcs = useQuery({ queryKey: [...base, "fc"], queryFn: ({ signal }) => listFcRegions(signal), retry: false });
  const defaults = useQuery({ queryKey: [...base, "defaults"], queryFn: ({ signal }) => getCreationDefaults(signal), retry: false });
  const channels = useQuery({ queryKey: [...base, "channels"], queryFn: ({ signal }) => listLogisticsChannels(signal), retry: false });
  const [logOpen, setLogOpen] = useState(false);
  const changes = useQuery({ queryKey: [...base, "changes"], queryFn: ({ signal }) => listSettingsChanges(signal), retry: false, enabled: logOpen });

  const [draft, setDraft] = useState<RuleRow[]>();
  const [ask, setAsk] = useState<Ask>();
  const [form] = Form.useForm<{ reason: string; effective_date: string }>();
  const [defaultsForm] = Form.useForm<CreationDefaults>();
  const save = useMutation({
    mutationFn: ({ a, reason, effective }: { a: Ask; reason: string; effective?: string }) => a.run(reason, effective),
    onSuccess: () => {
      message.success("已保存");
      setAsk(undefined);
      setDraft(undefined);
      void qc.invalidateQueries({ queryKey: base });
    },
    onError: (e) => message.error(settingsError(e)),
  });
  const openAsk = (a: Ask) => {
    form.resetFields();
    form.setFieldsValue({ effective_date: today(), reason: "" });
    setAsk(a);
  };

  const editing = draft !== undefined;
  const ruleRows = draft ?? rules.data?.rows ?? [];
  const setCell = (i: number, patch: Partial<RuleRow>) => setDraft((d) => d?.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const text = (key: keyof RuleRow, title: string, width: number) => ({
    title, dataIndex: key, width,
    render: (v: string, _r: RuleRow, i: number) =>
      editing && key !== "rule_key" ? <Input size="small" aria-label={title} value={v} onChange={(e) => setCell(i, { [key]: e.target.value })} /> : v || "—",
  });
  const num = (key: "days" | "remind_days", title: string) => ({
    title, dataIndex: key, width: 110,
    render: (v: number, _r: RuleRow, i: number) =>
      editing ? <InputNumber size="small" aria-label={title} min={0} max={365} value={v} onChange={(n) => setCell(i, { [key]: n ?? 0 })} /> : v,
  });
  const ruleColumns: ColumnsType<RuleRow> = [
    {
      title: "节点", dataIndex: "node", width: 200,
      render: (v: string, r, i) => (
        <Space size={4} wrap>
          {editing ? <Input size="small" aria-label="节点" value={v} onChange={(e) => setCell(i, { node: e.target.value })} /> : v}
          {!r.decided && <Tag color="gold">{SAMPLE_TAG}</Tag>}
        </Space>
      ),
    },
    text("region", "地区", 90),
    text("carrier", "承运商", 100),
    text("channel", "渠道", 100),
    num("days", "天数"),
    num("remind_days", "提前提醒天数"),
    text("row_effective_date", "生效日", 120),
    text("notify", "通知对象", 120),
    text("remark", "备注", 220),
  ];

  const fcColumns: ColumnsType<FcRegion> = [
    { title: "仓库 (FC)", dataIndex: "fc", width: 110 },
    { title: "名称", dataIndex: "name", width: 140, render: (v) => v ?? "—" },
    { title: "地址", width: 200, render: (_, r) => [r.city, r.state, r.zip].filter(Boolean).join(", ") || "—" },
    {
      title: "地区", dataIndex: "region", width: 200,
      render: (v: Region, r) => (
        <Space size={4}>
          <Select<Region>
            size="small"
            aria-label={`${r.fc} 地区`}
            value={v}
            disabled={!canManage}
            style={{ width: 90 }}
            options={REGIONS.map((x) => ({ value: x, label: x }))}
            onChange={(region) => openAsk({ title: `${r.fc} 改为 ${region}`, run: (reason) => updateFcRegion(r.fc, { region, name: r.name, reason }) })}
          />
          <Tag color={r.region_source === "saved" ? "blue" : "default"}>{r.region_source === "saved" ? "已保存" : "按州默认"}</Tag>
        </Space>
      ),
    },
    { title: "货件数", dataIndex: "shipments", width: 80 },
    { title: "最近修改", width: 160, render: (_, r) => (r.updated_by ? `${r.updated_by} · ${time(r.updated_at)}` : "—") },
  ];

  const channelColumns: ColumnsType<LogisticsChannel> = [
    { title: "物流商", dataIndex: "provider_name", width: 160, render: (v, r) => v ?? r.provider_id ?? "—" },
    { title: "渠道", dataIndex: "channel_name", width: 200, render: (v, r) => v ?? r.channel_id },
    { title: "运输方式", dataIndex: "method_name", width: 140, render: (v) => v ?? "—" },
    { title: "状态", dataIndex: "enabled", width: 80, render: (v: boolean) => (v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>) },
  ];

  const changeColumns: ColumnsType<SettingsChange> = [
    { title: "时间", dataIndex: "created_at", width: 140, render: (v) => time(v) },
    { title: "对象", width: 140, render: (_, r) => `${entityLabel[r.entity] ?? r.entity} · ${r.entity_key}` },
    { title: "原因", dataIndex: "reason", width: 200 },
    { title: "操作人", dataIndex: "actor", width: 120 },
  ];

  const writeButton = (label: string, onClick: () => void, primary = false) => (
    <Button type={primary ? "primary" : "default"} disabled={!canManage} title={writeHint} onClick={onClick}>{label}</Button>
  );
  const loadAlert = (error: unknown) => (error ? <Alert type="error" showIcon message={settingsError(error)} /> : null);
  const rs = rules.data;

  return (
    <PageShell
      page={page}
      headerActions={<Button href="/help/pmc-wfs.html" target="_blank" rel="noreferrer" icon={<QuestionCircleOutlined />}>帮助</Button>}
    >
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Alert
          showIcon
          type="info"
          message="数据来自新系统数据库"
          description="规则按版本保存，每次修改都要填原因并留痕。本页不调用领星，也不写入 Walmart。"
        />
        {!canManage && <Alert showIcon type="warning" message={`写入按钮已置灰：${writeHint}`} />}

        <Card
          title="① 异常与提醒规则"
          extra={(
            <Space wrap>
              {rs && <Typography.Text type="secondary">版本 v{rs.version.version_no} · 生效 {rs.version.effective_date}</Typography.Text>}
              <Button onClick={() => setLogOpen(true)}>版本与修改记录</Button>
              {editing ? (
                <>
                  <Button onClick={() => setDraft((d) => [...(d ?? []), newRow()])}>+ 新增规则</Button>
                  <Button onClick={() => setDraft(undefined)}>取消</Button>
                  {writeButton("保存为新版本", () => openAsk({
                    title: "保存为新规则版本", withDate: true,
                    run: (reason, effective) => createRuleVersion({ effective_date: effective ?? today(), reason, rows: draft ?? [] }),
                  }), true)}
                </>
              ) : writeButton("编辑规则", () => setDraft(rs?.rows.map((r) => ({ ...r }))))}
            </Space>
          )}
        >
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            {loadAlert(rules.error)}
            {rs && rs.sample_rows > 0 && (
              <Alert
                type="warning"
                showIcon
                message={`有 ${rs.sample_rows} 条规则按示例阈值执行（标「${SAMPLE_TAG}」），业务确认后改成正式值`}
              />
            )}
            <Table<RuleRow>
              size="small"
              rowKey={(r, i) => `${r.rule_key ?? "new"}-${i}`}
              loading={rules.isFetching}
              columns={ruleColumns}
              dataSource={ruleRows}
              pagination={false}
              scroll={{ x: 1200 }}
              onRow={(r) => (r.decided ? {} : { style: { background: "#fffbe6" } })}
            />
          </Space>
        </Card>

        <Card title="② 店铺设置">
          <Alert showIcon type="info" message="店铺设置等店铺来源 PR 合入主分支后接入（S1），本页暂不显示。" />
        </Card>

        <Card title="③ 仓库地区 (FC)">
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Typography.Text type="secondary">仓库来自 WFS 货件看板的收货地址；没保存过的仓库按所在州给默认地区。</Typography.Text>
            {loadAlert(fcs.error)}
            <Table<FcRegion>
              size="small" rowKey="fc" loading={fcs.isFetching} columns={fcColumns} dataSource={fcs.data ?? []}
              pagination={{ pageSize: 20, hideOnSinglePage: true }} scroll={{ x: 900 }}
              locale={{ emptyText: "看板上还没有仓库" }}
            />
          </Space>
        </Card>

        <Card title="④ 创建货件默认值">
          {loadAlert(defaults.error)}
          {defaults.data && (
            <Form<CreationDefaults>
              key={`${defaults.data.source_account_ref}-${defaults.data.updated_at ?? "seed"}`}
              form={defaultsForm}
              layout="inline"
              disabled={!canManage}
              initialValues={defaults.data}
              onFinish={(values) => openAsk({ title: "修改创建默认值", run: (reason) => updateCreationDefaults({ ...values, reason }) })}
            >
              <Form.Item label="运输方式" name="transport">
                <Select style={{ width: 120 }} options={Object.entries(transportLabel).map(([value, label]) => ({ value, label }))} />
              </Form.Item>
              <Form.Item label="发货日 = 今天 +" name="ship_date_offset"><InputNumber min={0} max={365} addonAfter="天" /></Form.Item>
              <Form.Item label="每托箱数" name="pallet_boxes"><InputNumber min={1} max={999} /></Form.Item>
              <Form.Item label="混装箱数" name="mixed_boxes"><InputNumber min={0} max={999} /></Form.Item>
              <Form.Item label="承运商" name="carrier_opt">
                <Radio.Group options={[{ value: "own", label: "自有承运商" }, { value: "wm", label: "Walmart 合作承运商" }]} />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit" title={writeHint}>保存默认值</Button>
              </Form.Item>
              <Typography.Text type="secondary">
                {defaults.data.saved ? `已保存 · ${defaults.data.updated_by ?? ""} ${time(defaults.data.updated_at)}` : "尚未保存，显示的是 8088 默认值"}
              </Typography.Text>
            </Form>
          )}
        </Card>

        <Card title="⑤ 物流渠道字典（只读）">
          {loadAlert(channels.error)}
          {channels.data && !channels.data.loaded ? (
            <Alert showIcon type="info" message="WFS 组尚未导入物流渠道文件，导入后在这里显示。" />
          ) : (
            <Table<LogisticsChannel>
              size="small" rowKey="channel_id" loading={channels.isFetching} columns={channelColumns}
              dataSource={channels.data?.items ?? []} pagination={{ pageSize: 20, hideOnSinglePage: true }}
            />
          )}
        </Card>

        <Card title="⑥ 通知">
          <Alert showIcon type="info" message="通知未接入：本期只保存「通知对象」文字，不发消息。" />
        </Card>

        <Card title="⑦ 口径说明">
          <Typography.Paragraph>
            上架缓冲天数（10 天）引用「自动补货」的规则，这里只读显示，修改请到自动补货设置。
          </Typography.Paragraph>
          <Typography.Paragraph type="secondary">
            规则改动保存为新版本，从生效日起使用；生效日之前的看板与异常仍按旧版本计算。地区与默认值的修改立即生效，并留修改记录。
          </Typography.Paragraph>
        </Card>
      </Space>

      <Modal
        open={ask !== undefined}
        title={ask?.title}
        okText="确认保存"
        cancelText="取消"
        confirmLoading={save.isPending}
        onCancel={() => setAsk(undefined)}
        onOk={() => form.validateFields().then((v) => ask && save.mutate({ a: ask, reason: v.reason, effective: v.effective_date }))}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          {ask?.withDate && (
            <Form.Item label="生效日" name="effective_date" rules={[{ required: true, message: "请选择生效日" }]}>
              <Input type="date" min={today()} />
            </Form.Item>
          )}
          <Form.Item label="修改原因" name="reason" rules={[{ required: true, min: 2, max: 500, message: "请填写 2–500 字的原因" }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer open={logOpen} onClose={() => setLogOpen(false)} title="版本与修改记录" width={720}>
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Table
            size="small"
            rowKey="version_no"
            loading={versions.isFetching}
            dataSource={versions.data ?? []}
            pagination={false}
            columns={[
              { title: "版本", dataIndex: "version_no", width: 70, render: (v) => `v${v}` },
              { title: "生效日", dataIndex: "effective_date", width: 110 },
              { title: "原因", dataIndex: "reason" },
              { title: "创建人", dataIndex: "created_by", width: 140 },
            ]}
          />
          {loadAlert(changes.error)}
          <Table<SettingsChange>
            size="small" rowKey={(r) => `${r.entity}-${r.entity_key}-${r.created_at}`} loading={changes.isFetching}
            columns={changeColumns} dataSource={changes.data?.items ?? []} pagination={{ pageSize: 20, hideOnSinglePage: true }}
            locale={{ emptyText: "还没有修改记录" }}
          />
        </Space>
      </Drawer>
    </PageShell>
  );
}

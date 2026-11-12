/**
 * 导入：上传卖家后台 / 接口下载的原始 CSV（结算报表 / 仓储费报表 / 入库运输报告），所有店铺都可以。
 * 系统按内容认类型；结算报表按 Partner ID 认店铺（没登记的要选店铺）；仓储 / 入库要选店铺；
 * 接口下载的仓储费报表没有汇总块，要填账期。每个文件单独回报结果。
 */
import { Alert, Button, DatePicker, Drawer, Select, Space, Table, Typography } from "antd";
import type { Dayjs } from "dayjs";
import { useRef, useState } from "react";
import { MAX_UPLOAD_BYTES, SOURCE_TEXT, uploadReport, wfsErrorText, type ApiImport } from "./wfsFeesApi";

interface UploadRow { key: string; name: string; result?: ApiImport; error?: string }

const summary = (row: UploadRow) => {
  if (row.error) return <Typography.Text type="danger">{row.error}</Typography.Text>;
  const r = row.result;
  if (!r) return <Typography.Text type="secondary">上传中…</Typography.Text>;
  if (r.status === "rejected") return <Typography.Text type="danger">拒收：{r.reject_reason}</Typography.Text>;
  const period = r.period_start ? ` ${r.period_start} ~ ${r.period_end}` : "";
  const head = `${SOURCE_TEXT[r.fee_source]}${period} · `;
  if (r.status === "empty") return <span>{head}<Typography.Text type="secondary">空报告，已记录（该期没有这类费用）</Typography.Text></span>;
  return <span>{head}{r.duplicate_of_file ? "同一份文件，已刷新 " : ""}新增 {r.rows_new} 行，重复 {r.rows_duplicate} 行{r.warnings.length ? <Typography.Text type="secondary">；{r.warnings.join("；")}</Typography.Text> : null}</span>;
};

function ImportDrawer({ open, stores, onClose, onDone }: { open: boolean; stores: [string, string][]; onClose: () => void; onDone: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [storeId, setStoreId] = useState<string>();
  const [period, setPeriod] = useState<[Dayjs, Dayjs] | null>(null);
  const [rows, setRows] = useState<UploadRow[]>([]);
  const [uploading, setUploading] = useState(false);
  const upload = async (files: File[]) => {
    if (!files.length) return;
    setUploading(true);
    const batch = crypto.randomUUID();
    setRows(files.map((file, index) => ({ key: `${batch}-${index}`, name: file.name })));
    for (const [index, file] of files.entries()) {
      const patch: Partial<UploadRow> = file.size > MAX_UPLOAD_BYTES
        ? { error: "超过 16MB，未上传" }
        : await uploadReport(file, { storeId, periodStart: period?.[0].format("YYYY-MM-DD"), periodEnd: period?.[1].format("YYYY-MM-DD") })
          .then((result) => ({ result }), (error: unknown) => ({ error: wfsErrorText(error) }));
      setRows((current) => current.map((row, position) => (position === index ? { ...row, ...patch } : row)));
    }
    setUploading(false);
    onDone();
  };
  return (
    <Drawer open={open} width={820} title="导入 WFS 费用报表" onClose={onClose}
      extra={<Button type="primary" loading={uploading} onClick={() => inputRef.current?.click()}>选择文件上传</Button>}>
      <input ref={inputRef} type="file" multiple accept=".csv,text/csv" style={{ display: "none" }} aria-label="选择报表文件" onChange={(event) => {
        const files = Array.from(event.target.files ?? []);
        event.target.value = "";
        void upload(files);
      }} />
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Space wrap>
          <Select allowClear showSearch placeholder="店铺（仓储 / 入库必选）" style={{ width: 200 }} value={storeId} optionFilterProp="label" options={stores.map(([id, code]) => ({ value: id, label: code }))} onChange={setStoreId} />
          <DatePicker.RangePicker placeholder={["账期起", "账期止"]} value={period} onChange={(value) => setPeriod(value as [Dayjs, Dayjs] | null)} />
          <Typography.Text type="secondary">账期只有「接口下载的仓储费报表」需要填；卖家后台下载的报表自带账期。</Typography.Text>
        </Space>
        {rows.length > 0 && <Table<UploadRow> rowKey="key" size="small" bordered pagination={false} dataSource={rows} columns={[
          { title: "文件", dataIndex: "name", width: 280, ellipsis: true },
          { title: "结果", render: (_, row) => summary(row) },
        ]} />}
        <Alert type="info" showIcon message="哪里下载" description={<ul className="fin-wfs__help-list">
          <li><b>结算报表</b>（服务费各类 + 退货处理费）：卖家后台 → 付款 → 对账单 → 服务费「查看详情」→ 下载；或接口下载的 SettlementReport_*.csv。系统按 Partner ID 认店铺。配送费行自动跳过。</li>
          <li><b>仓储费报表</b>：卖家后台 → WFS → 报告 → 仓储（Storage）→ 按账期下载原始 CSV（两周一期）。</li>
          <li><b>入库运输报告</b>：卖家后台 → WFS → 报告 → 入库运输（Inbound Transportation）→ 按账期下载。只对使用沃尔玛承运的货件收费，报告为空属正常，也要导。</li>
        </ul>} />
        <Typography.Paragraph type="secondary">系统按文件内容认类型，不看文件名。同一份文件再传只刷新不重复；仓储 / 入库同账期重传 = 覆盖，账期交叉但起止不同会拒收。被拒收的文件会写明原因，原件都留档。</Typography.Paragraph>
      </Space>
    </Drawer>
  );
}

export default ImportDrawer;
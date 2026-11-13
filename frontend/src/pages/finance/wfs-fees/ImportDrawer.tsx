/**
 * 导入（Rocky 11-13：不用任何选择，直接导入）：上传卖家后台 / 接口下载的原始 CSV，或卖家后台的 ZIP。
 * 系统按内容认报表类型，按 Partner ID / 文件里的商品认店铺，按报表自带的账期归期。
 * 认不出店铺的文件才在那一行给店铺下拉，选了重新导入（只补认不出的，认得出的不会被改）。
 */
import { Alert, Button, Drawer, Select, Space, Table, Typography } from "antd";
import { useRef, useState } from "react";
import { MAX_UPLOAD_BYTES, SOURCE_TEXT, uploadReport, wfsErrorText, type ApiImport } from "./wfsFeesApi";

interface UploadRow { key: string; file: File; results?: ApiImport[]; error?: string; storeId?: string; busy?: boolean }

const one = (r: ApiImport) => {
  if (r.status === "rejected") return <Typography.Text type="danger">拒收：{r.reject_reason}</Typography.Text>;
  const period = r.period_start ? ` ${r.period_start} ~ ${r.period_end}` : "";
  const head = `${SOURCE_TEXT[r.fee_source]}${period} · `;
  if (r.status === "empty") return <span>{head}<Typography.Text type="secondary">{r.warnings.length ? `没有要入表的费用：${r.warnings.join("；")}` : "空报告，已记录（该期没有这类费用）"}</Typography.Text></span>;
  return <span>{head}{r.duplicate_of_file ? "同一份文件，已刷新 " : ""}新增 {r.rows_new} 行，重复 {r.rows_duplicate} 行{r.warnings.length ? <Typography.Text type="secondary">；{r.warnings.join("；")}</Typography.Text> : null}</span>;
};

const summary = (row: UploadRow) => {
  if (row.error) return <Typography.Text type="danger">{row.error}</Typography.Text>;
  if (!row.results) return <Typography.Text type="secondary">上传中…</Typography.Text>;
  if (row.results.length === 1) return one(row.results[0]);
  // ZIP：里面每个 CSV 一行
  return <div>{row.results.map((r) => <div key={r.file_name}><Typography.Text type="secondary">{r.file_name.split("/").pop()}：</Typography.Text>{one(r)}</div>)}</div>;
};

const needsStore = (row: UploadRow) => Boolean(row.results?.some((r) => r.needs_store));

function ImportDrawer({ open, stores, onClose, onDone }: { open: boolean; stores: [string, string][]; onClose: () => void; onDone: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [rows, setRows] = useState<UploadRow[]>([]);
  const [uploading, setUploading] = useState(false);
  const patchRow = (key: string, patch: Partial<UploadRow>) => setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  const send = (file: File, storeId?: string): Promise<Partial<UploadRow>> => (file.size > MAX_UPLOAD_BYTES
    ? Promise.resolve({ error: "超过 16MB，未上传" })
    : uploadReport(file, { storeId }).then((results) => ({ results, error: undefined }), (error: unknown) => ({ error: wfsErrorText(error) })));
  const upload = async (files: File[]) => {
    if (!files.length) return;
    setUploading(true);
    const batch = crypto.randomUUID();
    const added = files.map((file, index) => ({ key: `${batch}-${index}`, file }));
    setRows(added);
    for (const row of added) patchRow(row.key, await send(row.file));
    setUploading(false);
    onDone();
  };
  const retry = async (row: UploadRow) => {
    patchRow(row.key, { busy: true });
    patchRow(row.key, { ...(await send(row.file, row.storeId)), busy: false });
    onDone();
  };
  return (
    <Drawer open={open} width={860} title="导入 WFS 费用报表" onClose={onClose}
      extra={<Button type="primary" loading={uploading} onClick={() => inputRef.current?.click()}>选择文件上传</Button>}>
      <input ref={inputRef} type="file" multiple accept=".csv,.zip,text/csv,application/zip" style={{ display: "none" }} aria-label="选择报表文件" onChange={(event) => {
        const files = Array.from(event.target.files ?? []);
        event.target.value = "";
        void upload(files);
      }} />
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Typography.Text>直接选文件上传，可以一次多选；不用选店铺、账期，系统自动识别。卖家后台下载的 ZIP 不用解压。</Typography.Text>
        {rows.length > 0 && <Table<UploadRow> rowKey="key" size="small" bordered pagination={false} dataSource={rows} columns={[
          { title: "文件", width: 260, ellipsis: true, render: (_, row) => row.file.name },
          { title: "结果", render: (_, row) => (
            <Space direction="vertical" size={6} style={{ width: "100%" }}>
              {summary(row)}
              {needsStore(row) && (
                <Space>
                  <Select size="small" showSearch placeholder="选店铺" style={{ width: 160 }} value={row.storeId} optionFilterProp="label"
                    options={stores.map(([id, code]) => ({ value: id, label: code }))} onChange={(value) => patchRow(row.key, { storeId: value })} />
                  <Button size="small" type="primary" disabled={!row.storeId} loading={row.busy} onClick={() => void retry(row)}>重新导入</Button>
                </Space>
              )}
            </Space>
          ) },
        ]} />}
        <Alert type="info" showIcon message="哪里下载" description={<ul className="fin-wfs__help-list">
          <li><b>结算报表</b>（服务费各类 + 退货处理费）：卖家后台 → 付款 → 对账单 → 服务费「查看详情」→ 下载；或接口下载的 SettlementReport_*.csv。配送费行自动跳过。</li>
          <li><b>仓储费报表</b>：卖家后台 → WFS → 报告 → 仓储（Storage）→ 按账期下载（两周一期）。</li>
          <li><b>入库运输报告</b>：卖家后台 → WFS → 报告 → 入库运输（Inbound Transportation）→ 按账期下载。只对使用沃尔玛承运的货件收费，报告为空属正常，也要导。</li>
        </ul>} />
        <Typography.Paragraph type="secondary">系统按文件内容认类型，不看文件名；按 Partner ID、文件里的商品认店铺。同一份文件再传只刷新不重复；仓储 / 入库同账期重传 = 覆盖，账期交叉但起止不同会拒收。被拒收的文件会写明原因，原件都留档。配送费报表不入这张表。</Typography.Paragraph>
      </Space>
    </Drawer>
  );
}

export default ImportDrawer;

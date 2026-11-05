/**
 * 日记账 ·「流水导入」抽屉（Rocky 2026-11-04：数据导入改为直接在日记账导入，不另开页面；原「数据导入」页保留、不上线）。
 * 内容取自「数据导入」的「现金流账户报表」一项：交表节点、文件格式、各账户最近一次导入与覆盖范围。
 * 开发环境读 imports.json，上传按钮置灰（LOCKED_TIP）；正式构建读接口，可以上传。交表人一律写角色。
 */
import { Alert, Button, Descriptions, Drawer, Space, Table, Tag, Tooltip, Typography } from "antd";
import { useRef, useState } from "react";
import { LOCKED_TIP } from "@/pages/finance/FinanceBoardFrame";
import { cashErrorText, nextImportNode, uploadStatement, useLiveJournal, useRefreshJournal, type ApiAccount, type ApiFileResult } from "@/pages/finance/cash-flow/journalApi";
import { useImportsSnapshot, type ImportDetail } from "@/pages/finance/localFinData";
import EmptyState from "@/shared/states/EmptyState";

/** 「现金流账户报表」在 imports.json 里的 id。 */
const BANK_IMPORT_ID = "bank";
const ACCEPT = ".xlsx,.xls,.csv";
const IMPORT_NODE_TEXT = "每周二 15:00 前，各账户导出「月初到今天」一次性全部上传";
const NAME_RULE = "原文件名即可（系统按内容认账户，不看文件名）；一次选全部文件";
const FORMAT_TEXT = "用银行网银或平台后台导出的交易明细原文件（xls、xlsx 或 csv），不要回单 PDF，也不要自己改过的表。每次导「本月 1 日到今天」，重复的流水自动去重。";

/** 和后端 FINANCE_CASHFLOW_MAX_UPLOAD_BYTES 默认值一致：超过的文件不上传。 */
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

interface UploadRow { key: string; name: string; result?: ApiFileResult; error?: string }

const uploadSummary = (row: UploadRow) => {
  if (row.error) return <Typography.Text type="danger">{row.error}</Typography.Text>;
  const result = row.result;
  if (!result) return <Typography.Text type="secondary">上传中…</Typography.Text>;
  if (result.status === "rejected") return <Typography.Text type="danger">拒收：{result.reject_reason}</Typography.Text>;
  if (result.duplicate_of_file) return <span>整份文件之前已导入过</span>;
  return <span>{result.account_keys.join("、")} · 新增 {result.rows_new} 行，重复 {result.rows_duplicate} 行{result.warnings.length ? <Typography.Text type="warning">（{result.warnings.join("；")}）</Typography.Text> : null}</span>;
};

function DrawerBody({ node, description, name, nextNode, cover, stale, details, missing, footer }: {
  node: string; description?: string; name: string; nextNode: string; cover?: string; stale?: boolean; details: ImportDetail[]; missing: number; footer: string;
}) {
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Alert type="info" showIcon message={node} description={description} />
      <Descriptions className="fin-cash-flow__import-desc" size="small" column={1} bordered>
        <Descriptions.Item label="导入内容">{name}</Descriptions.Item>
        <Descriptions.Item label="交表人">财务专员</Descriptions.Item>
        <Descriptions.Item label="下一个交表节点">{nextNode || "—"}</Descriptions.Item>
        <Descriptions.Item label="覆盖到">{cover ? <Tag bordered={false} color={stale ? "red" : "green"}>{cover}{stale ? " · 已过期" : ""}</Tag> : "—"}</Descriptions.Item>
        <Descriptions.Item label="接受类型">{ACCEPT}</Descriptions.Item>
        <Descriptions.Item label="文件名规则">{NAME_RULE}</Descriptions.Item>
        <Descriptions.Item label="格式要求">{FORMAT_TEXT}</Descriptions.Item>
        <Descriptions.Item label="用在">日记账</Descriptions.Item>
      </Descriptions>
      <div>
        <Typography.Text strong>各账户最近一次导入（{details.length} 个账户{missing ? `，${missing} 个还没导入过` : ""}）</Typography.Text>
        <Table<ImportDetail> className="fin-cash-flow__import-table" rowKey="t" size="small" bordered pagination={false} dataSource={details} columns={[
          { title: "账户", dataIndex: "t", width: 220 },
          { title: "最近文件", dataIndex: "file", width: 280, ellipsis: true, render: (value?: string) => value || "—" },
          { title: "行", dataIndex: "n", width: 70, align: "right", render: (value?: number) => value ?? "—" },
          { title: "覆盖", width: 240, render: (_, row) => (row.missing ? <Tag color="red" bordered={false}>还没导入过</Tag> : <span>{row.from} ~ {row.max_d}<Typography.Text type="secondary"> · {row.range_src === "表头" ? "表头声明" : "按首末笔"}</Typography.Text></span>) },
        ]} />
      </div>
      <Typography.Text type="secondary">{footer}</Typography.Text>
    </Space>
  );
}

function DemoImportDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const snapshot = useImportsSnapshot();
  const item = snapshot.data?.items.find((row) => row.id === BANK_IMPORT_ID);
  const details = item?.detail ?? [];
  return (
    <Drawer open={open} width={880} rootClassName="fin-cash-flow__drawer" title="流水导入" onClose={onClose}
      extra={<Tooltip title={LOCKED_TIP}><Button type="primary" disabled>上传文件</Button></Tooltip>}>
      {snapshot.isPending && <Typography.Text type="secondary">正在读取本地预览数据…</Typography.Text>}
      {snapshot.error && <EmptyState title="本地预览数据未就绪" description={(snapshot.error as Error).message} />}
      {snapshot.data && !item && <EmptyState title="没有流水导入的配置" description="imports.json 里没有「现金流账户报表」这一项" />}
      {item && <DrawerBody node={item.node} description={snapshot.data?.meta.note} name={item.name} nextNode={item.next_node ?? ""} cover={item.cover} stale={item.stale} details={details} missing={details.filter((row) => row.missing).length} footer="本地预览不能上传，按钮置灰；正式上传等流水导入的后端接口上线后开放。导入历史、失败记录以后也放在这里。" />}
    </Drawer>
  );
}

const toDetail = (row: ApiAccount): ImportDetail => ({
  t: row.display_name, file: row.last_file_name ?? undefined, n: row.line_count, from: row.cover_from ?? undefined, max_d: row.cover_to ?? undefined, range_src: row.cover_source ?? undefined, missing: !row.line_count,
});

function LiveImportDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const journal = useLiveJournal(true);
  const refresh = useRefreshJournal();
  const inputRef = useRef<HTMLInputElement>(null);
  const [rows, setRows] = useState<UploadRow[]>([]);
  const [uploading, setUploading] = useState(false);
  const accounts = journal.data?.accounts ?? [];
  const details = accounts.map(toDetail);
  const covers = accounts.map((row) => row.cover_to).filter((value): value is string => Boolean(value)).sort();
  const upload = async (files: File[]) => {
    if (!files.length) return;
    setUploading(true);
    const importId = crypto.randomUUID();
    const started = files.map((file, index): UploadRow => ({ key: `${importId}-${index}`, name: file.name }));
    setRows(started);
    for (const [index, file] of files.entries()) {
      if (file.size > MAX_UPLOAD_BYTES) {
        setRows((current) => current.map((row, position) => (position === index ? { ...row, error: "超过 20MB，未上传" } : row)));
        continue;
      }
      const patch: Partial<UploadRow> = await uploadStatement(file, importId).then((result) => ({ result }), (error: unknown) => ({ error: cashErrorText(error) }));
      setRows((current) => current.map((row, position) => (position === index ? { ...row, ...patch } : row)));
    }
    setUploading(false);
    void refresh();
  };
  return (
    <Drawer open={open} width={880} rootClassName="fin-cash-flow__drawer" title="流水导入" onClose={onClose}
      extra={<Button type="primary" loading={uploading} onClick={() => inputRef.current?.click()}>上传文件</Button>}>
      <input ref={inputRef} type="file" multiple accept={ACCEPT} style={{ display: "none" }} aria-label="选择流水文件" onChange={(event) => {
        const files = Array.from(event.target.files ?? []);
        event.target.value = "";
        void upload(files);
      }} />
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        {rows.length > 0 && <Table<UploadRow> className="fin-cash-flow__import-table" rowKey="key" size="small" bordered pagination={false} dataSource={rows} columns={[
          { title: "文件", dataIndex: "name", width: 280, ellipsis: true },
          { title: "结果", render: (_, row) => uploadSummary(row) },
        ]} />}
        {journal.error && <EmptyState title="账户读取失败" description={cashErrorText(journal.error)} />}
        <DrawerBody node={IMPORT_NODE_TEXT} name="现金流账户报表（银行 / 平台原始导出）" nextNode={nextImportNode(new Date())} cover={covers[covers.length - 1]} details={details} missing={details.filter((row) => row.missing).length} footer="系统按文件内容认账户，重复的流水自动去重；被拒收的文件会写明原因。导入历史、失败记录以后也放在这里。" />
      </Space>
    </Drawer>
  );
}

function ImportDrawer({ open, live, onClose }: { open: boolean; live?: boolean; onClose: () => void }) {
  return live ? <LiveImportDrawer open={open} onClose={onClose} /> : <DemoImportDrawer open={open} onClose={onClose} />;
}

export default ImportDrawer;

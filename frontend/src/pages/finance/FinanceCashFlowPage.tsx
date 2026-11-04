/**
 * 财务 · 资金流水（本地预览阶段 A，只读）。左侧菜单「资金流水」：账户总览（按月）/ 日记账（备货资金暂从菜单隐藏，代码保留）。
 * 2026-11-04 Rocky：去掉「异常」页，资金异常全部并入日记账显示，不分等级（所有异常都要处理）。
 * 视觉与 PMC 采购看板一致：page card → 标题行 → 筛选卡（ReportFacetSelect / CommittedSearch / 重置）→ 统计卡（ManagementStatCards，点击即筛选）→ ProTable。
 * 数据来自 localFinData（Demo 快照）；正式接口（PR-E）上线后替换；所有写操作置灰。
 */
import { CheckOutlined, CloseOutlined, SettingOutlined } from "@ant-design/icons";
import { Alert, AutoComplete, Button, Descriptions, Divider, Drawer, Image, Input, Modal, Select, Space, Table, Tag, Tooltip, Typography, message } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageShell from "@/components/page/PageShell";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResetButton from "@/components/report-table/ResetButton";
import RuntimeColumnConfigDrawer, { type RuntimeColumnGroup } from "@/components/report-table/RuntimeColumnConfigDrawer";
import type { NavigationPage } from "@/config/navigation";
import FinanceBoardFrame, { FinMoney, LOCKED_TIP } from "@/pages/finance/FinanceBoardFrame";
import CashStockBoard, { CashStockHelp } from "@/pages/finance/cash-flow/CashStockBoard";
import ImportDrawer from "@/pages/finance/cash-flow/ImportDrawer";
import { ALERT_GUIDE, alertShort, fsFileUrl, toCashAlerts, useApprovals, useStock, type CashAlert, type FsDetail, type FsRecord } from "@/pages/finance/cash-flow/data";
import "@/pages/finance/cash-flow/cash-flow.css";
import {
  accountLabel,
  fmtMoney,
  useCashSnapshot,
  type CashAccount,
  type CashFlowMonth,
  type CashLine,
  type CashSnapshot,
  type FeishuApproval,
} from "@/pages/finance/localFinData";
import ReportFacetSelect from "@/shared/report-filters";
import EmptyState from "@/shared/states/EmptyState";
import { readUserPreference, writeUserPreference } from "@/shared/preferences/userPreferenceCache";

export type CashFlowView = "accounts" | "journal" | "stock";
type ReviewCard = "all" | "todo" | "ok1" | "ok2" | "uncat" | "alert" | "excluded" | "fs_open";

const HANDOFF_KEY = "finance:cash-journal:handoff";
const OPEN_STATES = ["未付", "部分已付", "金额不符", "金额缺失"];
const STATE_COLOR: Record<string, string> = { 已付: "green", 未付: "red", 部分已付: "orange", 金额不符: "volcano", 已取消: "default", 金额缺失: "purple" };
const KIND_COLOR: Record<string, string> = { 对公: "blue", 对私: "orange", 现金: "orange", 平台: "purple", 其他: "gold" };
const EMPTY = "—";

/* 审批单未付（Rocky 11-02 20:02）：只算流水起始月及以后发起、已审批通过的单；之前的单当时已在系统外付款，不算未付。 */
const isOpenApproval = (item: FeishuApproval, data: CashSnapshot) => OPEN_STATES.includes(item.state) && item.status === "已同意" && (item.start || "") >= `${data.meta.start}-01`;
const isExcluded = (line: CashLine) => line.cat === "X01" || Boolean(line.excl) || Boolean(line.parts?.some((part) => part.cat === "X01"));
/* 审核：初审（财务专员）→ 终审（财务主管）。初审不通过留在专员处；终审不通过驳回到待初审，都必须填原因。 */
type ReviewStage = "todo" | "rej1" | "ok1" | "rej2" | "ok2";
interface ReviewMark { stage: ReviewStage; reason?: string; note?: string }
const REVIEW_TAG: Record<ReviewStage, { color: string; text: string }> = {
  todo: { color: "default", text: "待初审" },
  rej1: { color: "red", text: "初审不通过" },
  ok1: { color: "blue", text: "待终审" },
  rej2: { color: "volcano", text: "终审驳回 · 待初审" },
  ok2: { color: "green", text: "已终审" },
};
const baseReview = (line: CashLine): ReviewMark => ({ stage: line.ok2 ? "ok2" : line.ok ? "ok1" : "todo" });
const isFirstPending = (stage: ReviewStage) => stage === "todo" || stage === "rej1" || stage === "rej2";
const REVIEW_STAGE_OPTIONS = (Object.keys(REVIEW_TAG) as ReviewStage[]).map((stage) => ({ value: stage, label: REVIEW_TAG[stage].text }));
const PREVIEW_ACTION_TIP = "本地预览：审核只记在本页，刷新即还原，不写库";

/* ---------------------------------------------------------------- 关联审批单：字段 + 凭证 + 与流水逐项比对（Rocky 11-03 定稿）
 * 日记账不强制匹配审批单（没有就显示「无审批单」）；审批金额和流水金额有差额，初审必须写差额说明，终审看得到。
 * 比对只用文字字段：金额、收款人 vs 对方、收款账号尾号 vs 对方账号尾号、办理完成时间 vs 付款日期；不一致标红，图片给主管目视核对。第一版不做 OCR。 */
interface ApprovalView {
  serial: string; kind: string; status: string; state?: string; start: string; end: string; handled: string; applicant: string;
  reason: string; amount: number | null; cur: string; payee: string; bank: string; last4: string; invoice: string; pay: string;
  items: { c: string; a: number | null }[]; detail?: FsDetail; masked: boolean; known: boolean;
}
const viewOf = (serial: string, item?: FeishuApproval, detail?: FsDetail): ApprovalView => ({
  serial,
  kind: detail?.kind || item?.kind || "",
  status: detail?.status || item?.status || "",
  state: item?.state,
  start: detail?.start || item?.start || "",
  end: detail?.end || item?.end || "",
  handled: detail?.handled || "",
  applicant: detail?.applicant || item?.applicant || "",
  reason: detail?.reason || item?.reason || "",
  amount: detail?.amount ?? item?.amount ?? null,
  cur: detail?.cur || item?.cur || "CNY",
  payee: detail?.payee || item?.payee || "",
  bank: detail?.bank || item?.bank || "",
  last4: detail?.last4 || item?.last4 || "",
  invoice: detail?.invoice || item?.invoice || "",
  pay: detail?.pay || item?.pay || "",
  items: detail?.items.length ? detail.items : item?.items ?? [],
  detail,
  masked: Boolean(item?.masked),
  known: Boolean(item || detail),
});
const norm = (text?: string) => (text ?? "").replace(/[\s()（）·.,，、]/g, "").toLowerCase();
const dayGap = (a: string, b: string) => Math.round(Math.abs(Date.parse(a.slice(0, 10)) - Date.parse(b.slice(0, 10))) / 86400000);
/** 审批金额合计 − 流水金额（取绝对值）；没有审批单或审批单没金额时为 null。 */
const amountDiff = (line: CashLine, views: ApprovalView[]) => {
  const amounts = views.map((view) => view.amount).filter((value): value is number => value != null);
  if (!views.length || !amounts.length || line.amt == null) return null;
  return Math.round((amounts.reduce((sum, value) => sum + value, 0) - Math.abs(line.amt)) * 100) / 100;
};
interface CompareRow { key: string; item: string; approval: string; line: string; ok: boolean | null; result: string }
const compareRows = (line: CashLine, views: ApprovalView[]): CompareRow[] => {
  const diff = amountDiff(line, views);
  const rows: CompareRow[] = [{
    key: "amt", item: "金额", approval: views.map((view) => (view.amount == null ? "没金额" : fmtMoney(view.amount, view.cur))).join(" + "), line: fmtMoney(line.amt == null ? null : Math.abs(line.amt), line.cur),
    ok: diff == null ? null : Math.abs(diff) < 0.005, result: diff == null ? "审批单没金额" : Math.abs(diff) < 0.005 ? "一致" : `差额 ${fmtMoney(diff, line.cur)}`,
  }];
  views.forEach((view) => {
    const tag = views.length > 1 ? ` · ${view.serial}` : "";
    const payeeOk = !view.payee || !line.party ? null : norm(view.payee) === norm(line.party) || norm(line.party).includes(norm(view.payee)) || norm(view.payee).includes(norm(line.party));
    rows.push({ key: `payee-${view.serial}`, item: `收款人 / 对方${tag}`, approval: view.payee || EMPTY, line: line.party || EMPTY, ok: payeeOk, result: payeeOk == null ? "缺一边，看凭证" : payeeOk ? "一致" : "不一致" });
    rows.push({ key: `last4-${view.serial}`, item: `账号尾号${tag}`, approval: view.last4 ? `…${view.last4}` : EMPTY, line: EMPTY, ok: null, result: "流水暂无对方账号（银行明细还没取这一列），看凭证" });
    const done = view.handled || view.end;
    const gap = done ? dayGap(done, line.date) : null;
    rows.push({ key: `time-${view.serial}`, item: `办理完成 / 付款日期${tag}`, approval: done || EMPTY, line: `${line.date} ${line.time ?? ""}`.trim(), ok: gap == null ? null : gap <= 1, result: gap == null ? "审批单还没办理完成" : gap <= 1 ? (gap ? "差 1 天（银行入账次日，算一致）" : "同一天") : `差 ${gap} 天` });
  });
  return rows;
};

function CompareTable({ rows }: { rows: CompareRow[] }) {
  const cell = (row: CompareRow, text: string) => (row.ok === false ? <Typography.Text type="danger">{text}</Typography.Text> : text);
  return (
    <Table<CompareRow> size="small" bordered pagination={false} rowKey="key" dataSource={rows} columns={[
      { title: "比对项", dataIndex: "item", width: 150 },
      { title: "审批单", dataIndex: "approval", render: (_, row) => cell(row, row.approval) },
      { title: "流水", dataIndex: "line", render: (_, row) => cell(row, row.line) },
      { title: "结果", dataIndex: "result", width: 170, render: (_, row) => (row.ok === false ? <Tag color="red" bordered={false}>{row.result}</Tag> : row.ok ? <Tag color="green" bordered={false}>{row.result}</Tag> : <Typography.Text type="secondary">{row.result}</Typography.Text>) },
    ]} />
  );
}

/** 一张审批单：字段 + 明细 + 凭证（截图 / 付款凭证 / 附件）。 */
function ApprovalPanel({ view, onOpen }: { view: ApprovalView; onOpen?: () => void }) {
  const hide = (value: string) => (view.masked ? "****" : value || EMPTY);
  const files = view.detail?.files ?? [];
  const images = files.filter((file) => file.img);
  const others = files.filter((file) => !file.img);
  return (
    <div className="fin-cash-flow__approval">
      <Descriptions size="small" column={1} bordered title={<Space size={8}>{onOpen ? <Button type="link" size="small" style={{ padding: 0 }} onClick={onOpen}>{view.serial}</Button> : view.serial}<Typography.Text type="secondary">{view.kind || "飞书里没找到这张单"}</Typography.Text>{view.status && <Tag bordered={false}>{view.status}</Tag>}{view.state && <Tag bordered={false} color={STATE_COLOR[view.state]}>{view.state}</Tag>}</Space>}>
        <Descriptions.Item label="申请人">{view.applicant || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="发起 / 办理完成">{view.start || EMPTY} / {view.handled || view.end || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="事由">{hide(view.reason)}</Descriptions.Item>
        <Descriptions.Item label="审批金额"><FinMoney value={view.amount} cur={view.cur} masked={view.masked} /></Descriptions.Item>
        <Descriptions.Item label="收款人">{view.payee || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="收款银行 / 尾号">{view.bank || EMPTY}{view.last4 ? ` …${view.last4}` : ""}</Descriptions.Item>
        <Descriptions.Item label="付款方式 / 发票">{view.pay || EMPTY} / {view.invoice || EMPTY}</Descriptions.Item>
        {view.items.length > 0 && <Descriptions.Item label="费用明细">{view.items.map((row, index) => <div key={`${row.c}-${index}`}>{index + 1}. {hide(row.c)} <FinMoney value={row.a} masked={view.masked} /></div>)}</Descriptions.Item>}
      </Descriptions>
      {(view.detail?.records?.length ?? 0) > 0 && (
        <div className="fin-cash-flow__section">
          <Typography.Text strong>审批记录</Typography.Text>
          <Table<FsRecord> className="fin-cash-flow__records" size="small" bordered pagination={false} rowKey={(row) => `${row.time}-${row.node}-${row.who}-${row.act}`} dataSource={view.detail?.records}
            columns={[
              { title: "节点", dataIndex: "node", width: 70 },
              { title: "处理人", dataIndex: "who", width: 130, render: (_, row) => row.who || EMPTY },
              { title: "结果", dataIndex: "act", width: 80, render: (_, row) => <Tag bordered={false} color={row.act === "拒绝" || row.act === "退回" ? "red" : row.act === "撤回" ? "default" : row.act === "通过" || row.act === "自动通过" ? "green" : "blue"}>{row.act}</Tag> },
              { title: "时间", dataIndex: "time", width: 140 },
              { title: "意见 / 上传", dataIndex: "note", render: (_, row) => <>{row.note || ""}{row.files ? <Typography.Text type="secondary">{row.note ? "；" : ""}上传 {row.files} 个文件（见下方凭证）</Typography.Text> : row.note ? null : EMPTY}</> },
            ]} />
        </div>
      )}
      {(view.detail?.comments?.length ?? 0) > 0 && (
        <div className="fin-cash-flow__section">
          <Typography.Text strong>评论</Typography.Text>
          {view.detail?.comments?.map((row, index) => <div key={`${row.time}-${index}`}><Typography.Text type="secondary">{row.time} {row.who || "—"}：</Typography.Text>{row.note || "（只有附件）"}</div>)}
        </div>
      )}
      <div className="fin-cash-flow__section">
        <Typography.Text strong>凭证（{files.length}）</Typography.Text>
        <Typography.Text type="secondary" style={{ marginLeft: 8 }}>原图只有「财务 · 日记账初审 / 终审」权限的人能看（本地预览不分权限）</Typography.Text>
        {!view.detail
          ? <div><Typography.Text type="secondary">这张单的截图和付款凭证还没从飞书拉下来（正式版审批通过后自动同步）。</Typography.Text></div>
          : files.length === 0
            ? <div><Typography.Text type="secondary">飞书上这张单没有截图或附件。</Typography.Text></div>
            : <>
              <Image.PreviewGroup>
                <div className="fin-cash-flow__thumbs">
                  {images.map((file) => (
                    <span key={file.name} className="fin-cash-flow__thumb">
                      <Image width={104} height={104} src={fsFileUrl(file.name)} alt={`${view.serial} ${file.what}`} />
                      <Typography.Text type="secondary" ellipsis={{ tooltip: file.what }}>{file.item ? `明细${file.item} · ` : ""}{file.what}</Typography.Text>
                    </span>
                  ))}
                </div>
              </Image.PreviewGroup>
              {others.length > 0 && <div className="fin-cash-flow__section"><Typography.Text type="secondary">附件（PDF 点开在新窗口看，Excel 点开下载）：</Typography.Text>{others.map((file) => <div key={file.name}><a href={fsFileUrl(file.name)} target="_blank" rel="noreferrer">{file.what}：{file.title && file.title !== "<nil>" ? file.title : file.name}</a></div>)}</div>}
            </>}
      </div>
    </div>
  );
}

/* 日记账列配置：日期在左、审核状态 + 审核在右，三者固定。配对 / 标记不在表格展示（Rocky 11-02 19:13），详情里只读保留。 */
const JOURNAL_COLUMN_PREF_KEY = "finance-cash-journal:columns";
const JOURNAL_COLUMN_PREF_VERSION = 4;
const JOURNAL_FIXED_KEYS = ["date", "review"];
const JOURNAL_DEFAULT_KEYS = ["date", "acct", "sum", "memo", "party", "amt", "alert", "cny", "bal", "cat", "refs", "review"];
const JOURNAL_COLUMN_GROUPS: RuntimeColumnGroup[] = [
  { title: "流水", fields: [{ key: "date", title: "日期" }, { key: "acct", title: "账户" }, { key: "sum", title: "摘要" }, { key: "memo", title: "备注" }, { key: "party", title: "对方" }] },
  { title: "金额", fields: [{ key: "amt", title: "金额" }, { key: "cny", title: "折人民币" }, { key: "bal", title: "余额" }] },
  { title: "分类与单据", fields: [{ key: "cat", title: "类别" }, { key: "refs", title: "审批单" }, { key: "alert", title: "异常" }] },
  { title: "审核", fields: [{ key: "review", title: "审核状态 + 审核按钮（固定右侧）" }] },
];
const readJournalColumns = () => {
  const stored = readUserPreference<string[]>("anonymous", JOURNAL_COLUMN_PREF_KEY, JOURNAL_COLUMN_PREF_VERSION);
  return stored?.length ? stored : JOURNAL_DEFAULT_KEYS;
};

const icon = (text: string) => <span className="management-stat-card__mark">{text}</span>;
const scrollX = <T,>(columns: ProColumns<T>[]) => columns.reduce((sum, column) => sum + Number(column.width ?? 120), 0);

function BoardTable<T extends object>({ label, rowKey, rows, columns, emptyTitle, emptyText, pageSize = 50 }: {
  label: string; rowKey: string | ((row: T) => string); rows: T[]; columns: ProColumns<T>[]; emptyTitle: string; emptyText: string; pageSize?: number;
}) {
  return (
    <ReportTableShell label={label}>
      <ProTable<T>
        rowKey={rowKey}
        search={false}
        options={false}
        toolBarRender={false}
        tableAlertRender={false}
        bordered
        size="small"
        dataSource={rows}
        columns={columns}
        scroll={{ x: scrollX(columns), y: "100%" }}
        locale={{ emptyText: <EmptyState title={emptyTitle} description={emptyText} compact /> }}
        pagination={{ defaultPageSize: pageSize, showSizeChanger: true, showQuickJumper: true, showTotal: (count) => `共 ${count.toLocaleString()} 条` }}
      />
    </ReportTableShell>
  );
}

function writeHandoff(value: { account?: string; card?: ReviewCard }) {
  try { sessionStorage.setItem(HANDOFF_KEY, JSON.stringify(value)); } catch { /* 便利功能，失败忽略 */ }
}
function readHandoff(): { account?: string; card?: ReviewCard } {
  try {
    const raw = sessionStorage.getItem(HANDOFF_KEY);
    sessionStorage.removeItem(HANDOFF_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

/* ======================================================= 审批单详情抽屉 */
function ApprovalDrawer({ item, data, details, onClose }: { item?: FeishuApproval; data: CashSnapshot; details: Record<string, FsDetail>; onClose: () => void }) {
  if (!item) return null;
  const lines = new Map(data.lines.map((line) => [line.id, line]));
  const accounts = new Map(data.accounts.map((account) => [account.id, account.name]));
  const hide = (value: string) => (item.masked ? "****" : value || EMPTY);
  return (
    <Drawer open width={640} rootClassName="fin-cash-flow__drawer" onClose={onClose} title={<Space>飞书审批单 {item.serial}<Tag bordered={false} color={STATE_COLOR[item.state]}>{item.state}</Tag></Space>}>
      {details[item.serial] ? <ApprovalPanel view={viewOf(item.serial, item, details[item.serial])} /> : <>
      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="类型">{item.kind}</Descriptions.Item>
        <Descriptions.Item label="飞书状态">{item.status}</Descriptions.Item>
        <Descriptions.Item label="发起 / 完成">{item.start || EMPTY} / {item.end || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="申请人">{item.applicant || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="事由">{hide(item.reason)}</Descriptions.Item>
        <Descriptions.Item label="金额"><FinMoney value={item.amount} cur={item.cur} masked={item.masked} /></Descriptions.Item>
        <Descriptions.Item label="付款方式">{item.pay || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="收款人">{item.payee || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="收款银行">{item.bank ? `${item.bank}${item.last4 ? ` …${item.last4}` : ""}` : EMPTY}</Descriptions.Item>
        <Descriptions.Item label="发票">{item.invoice || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="关联单号">{item.rel || EMPTY}</Descriptions.Item>
      </Descriptions>
      {item.items.length > 0 && (
        <>
          <Divider orientation="left" plain>明细</Divider>
          <ProTable<{ c: string; a: number | null }> rowKey={(row) => `${row.c}-${row.a}`} search={false} options={false} toolBarRender={false} pagination={false} bordered size="small" dataSource={item.items}
            columns={[{ title: "明细", dataIndex: "c", render: (_, row) => hide(row.c) }, { title: "金额", dataIndex: "a", width: 140, align: "right", render: (_, row) => <FinMoney value={row.a} masked={item.masked} /> }]} />
        </>
      )}
      </>}
      <Divider orientation="left" plain>付款流水（{item.paid.length}）</Divider>
      {item.paid.length ? item.paid.map((paid) => {
        const line = lines.get(paid.line);
        return <div key={paid.line}><Tag bordered={false} color="blue">{paid.line}</Tag>{line ? `${line.date} ${accounts.get(line.acct) ?? line.acct} ` : ""}<FinMoney value={paid.amt ?? null} masked={item.masked} /></div>;
      }) : <Typography.Text type="secondary">还没对上付款流水</Typography.Text>}
      <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>来源：{data.meta.feishu_src.join("；")}。正式系统由飞书审批 API 同步。</Typography.Paragraph>
    </Drawer>
  );
}

/* ======================================================= 异常（并入日记账；不分等级，所有异常都要处理） */
function AlertSection({ alerts }: { alerts: CashAlert[] }) {
  const real = alerts.filter((item) => !item.hint);
  const hints = alerts.filter((item) => item.hint);
  if (!alerts.length) return null;
  return (
    <>
      <Divider orientation="left">异常（{real.length}）</Divider>
      <div className="fin-cash-flow__alerts">
        {real.map((item) => (
          <div key={item.id} className="fin-cash-flow__alert">
            <Space size={8} wrap><Tag color="red" bordered={false}>{alertShort(item.type)}</Tag><Typography.Text type="secondary">编号 {item.ref}</Typography.Text></Space>
            <Typography.Paragraph className="fin-cash-flow__alert-msg">{item.msg}</Typography.Paragraph>
            {ALERT_GUIDE[item.type] && <Typography.Text type="secondary">处理：{ALERT_GUIDE[item.type].guide}</Typography.Text>}
          </div>
        ))}
        {hints.map((item) => (
          <div key={item.id} className="fin-cash-flow__alert">
            <Space size={8} wrap><Tag bordered={false}>{item.type}</Tag><Typography.Text type="secondary">数据提示，不算异常</Typography.Text></Space>
            <Typography.Paragraph type="secondary" className="fin-cash-flow__alert-msg">{item.msg}</Typography.Paragraph>
          </div>
        ))}
      </div>
    </>
  );
}

/* ======================================================= 流水详情抽屉
 * 顺序（Rocky 11-03）：流水字段 → 关联审批单（比对 + 字段 + 凭证）→ 底部终审按钮。终审一笔一笔点；终审不通过必填原因，驳回到待初审。 */
function LineDrawer({ line, review, data, details, approvalsOf, alerts, onClose, onOpenApproval, onPass, onReject }: {
  line?: CashLine; review?: ReviewMark; data: CashSnapshot; alerts: CashAlert[]; details: Record<string, FsDetail>; approvalsOf: (line: CashLine) => ApprovalView[];
  onClose: () => void; onOpenApproval: (item: FeishuApproval) => void; onPass: (line: CashLine) => void; onReject: (line: CashLine) => void;
}) {
  if (!line) return null;
  const account = data.accounts.find((item) => item.id === line.acct);
  const cat = data.cats.find((item) => item.code === line.cat);
  const approvals = new Map(data.feishu.map((item) => [item.serial, item]));
  const mark = review ?? baseReview(line);
  const views = approvalsOf(line);
  const finalTurn = mark.stage === "ok1";
  const turnTip = finalTurn ? "" : mark.stage === "ok2" ? "已终审" : "还没初审通过，轮不到终审";
  return (
    <Drawer open width={720} rootClassName="fin-cash-flow__drawer" onClose={onClose} title={`流水 ${line.date} · ${accountLabel(account) || line.acct}`}
      extra={<Tooltip title={LOCKED_TIP}><Space><Button disabled>拆分</Button><Button danger disabled>剔除</Button></Space></Tooltip>}
      footer={<div className="fin-cash-flow__footer">
        <Tooltip title={turnTip || PREVIEW_ACTION_TIP}><Button type="primary" icon={<CheckOutlined aria-hidden="true" />} disabled={!finalTurn} onClick={() => onPass(line)}>终审通过</Button></Tooltip>
        <Tooltip title={turnTip || "必填原因，驳回到待初审"}><Button danger icon={<CloseOutlined aria-hidden="true" />} disabled={!finalTurn} onClick={() => onReject(line)}>终审不通过</Button></Tooltip>
      </div>}>
      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="流水 id">{line.id}</Descriptions.Item>
        <Descriptions.Item label="日期 / 时间">{line.date} {line.time ?? ""}</Descriptions.Item>
        <Descriptions.Item label="金额"><FinMoney value={line.amt} cur={line.cur} masked={line.masked} /></Descriptions.Item>
        {line.cur !== "CNY" && <Descriptions.Item label="折人民币"><FinMoney value={line.cny} masked={line.masked} /></Descriptions.Item>}
        <Descriptions.Item label="余额"><FinMoney value={line.bal ?? null} cur={line.cur} masked={line.masked} /></Descriptions.Item>
        <Descriptions.Item label="摘要">{line.masked ? "****" : line.sum || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="备注">{line.masked ? "****" : line.memo || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="对方">{line.party || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="类别">{line.cat ? `${line.cat} ${cat?.big ?? ""}·${cat?.name ?? ""}` : <Tag color="red" bordered={false}>待分类</Tag>}<Typography.Text type="secondary">（来源：{line.cat_src || "—"}）</Typography.Text></Descriptions.Item>
        <Descriptions.Item label="配对">{line.pair || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="标记">{line.flags.length ? line.flags.map((flag) => <Tag key={flag} bordered={false}>{flag}</Tag>) : EMPTY}</Descriptions.Item>
        <Descriptions.Item label="审核"><Tag bordered={false} color={REVIEW_TAG[mark.stage].color}>{REVIEW_TAG[mark.stage].text}</Tag>{mark.reason && <Typography.Text type="danger">原因：{mark.reason}</Typography.Text>}</Descriptions.Item>
      </Descriptions>
      <AlertSection alerts={alerts} />
      <Divider orientation="left">关联审批单（{line.refs.length}）</Divider>
      {views.length === 0 ? <Typography.Text type="secondary">无审批单。日记账不强制匹配审批单，照样可以初审、终审。</Typography.Text> : <>
        <CompareTable rows={compareRows(line, views)} />
        {(amountDiff(line, views) ?? 0) !== 0 && (
          <div className="fin-cash-flow__section">
            <Typography.Text strong>差额说明（初审填）：</Typography.Text>
            {mark.note ? <Typography.Text>{mark.note}</Typography.Text> : <Typography.Text type="danger">还没填。初审通过时必须写。</Typography.Text>}
          </div>
        )}
        <div className="fin-cash-flow__section">
          {views.map((view) => <ApprovalPanel key={view.serial} view={view} onOpen={approvals.get(view.serial) ? () => onOpenApproval(approvals.get(view.serial) as FeishuApproval) : undefined} />)}
        </div>
      </>}
      <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>类别、关联审批单在表格行上直接改；初审在表格右侧 ✓ ✗，终审可以在这里点。审核后再改类别 / 关联审批单 / 拆分 / 剔除会自动退回待初审。{Object.keys(details).length ? "" : "（审批单凭证数据没读到：先在 Mac 上运行 local_export/cash-flow.py）"}</Typography.Paragraph>
    </Drawer>
  );
}

/* ======================================================= 账户总览（按月） */
function AccountsBoard({ data }: { data: CashSnapshot }) {
  const navigate = useNavigate();
  const months = data.flow.months;
  const [month, setMonth] = useState(months[months.length - 1] ?? "");
  const fx = data.meta.fx[month]?.[0] ?? 7;
  const coverage = useMemo(() => {
    const out: Record<string, { from: string; to: string; src: string }> = {};
    (data.meta.bank_files ?? []).forEach((file) => {
      (file.accts ?? (file.acct ? [file.acct] : [])).forEach((acct) => {
        const next = { from: file.range_from || file.from || "", to: file.range_to || file.to || "", src: file.range_src || "流水" };
        if (!out[acct] || next.to > out[acct].to) out[acct] = next;
      });
    });
    return out;
  }, [data]);
  type Row = CashAccount & CashFlowMonth & { n_lines: number; uncat: number };
  const rows: Row[] = data.accounts.map((account) => {
    const lines = data.lines.filter((line) => line.acct === account.id && line.m === month);
    return { ...account, ...(data.flow.by_acct[account.id]?.[month] ?? {}), n_lines: lines.length, uncat: lines.filter((line) => !line.cat).length };
  });
  const toCny = (row: Row, value: number | null | undefined) => (value == null ? 0 : row.cur === "USD" ? value * fx : value);
  const inExt = rows.reduce((total, row) => total + toCny(row, row.in_ext), 0);
  const outExt = rows.reduce((total, row) => total + toCny(row, row.out_ext), 0);
  const unpaid = data.feishu.filter((item) => isOpenApproval(item, data)).length;
  const uncat = data.lines.filter((line) => line.m === month && !line.cat).length;
  const openJournal = (handoff: { account?: string; card?: ReviewCard }) => { writeHandoff(handoff); navigate("/finance/cash/journal"); };
  const cards: ManagementStatCardItem<string>[] = [
    { key: "in", title: `${month} 外部流入`, subtitle: "折人民币 · 不含内部调拨 / 结汇 / 归集", value: fmtMoney(inExt), tone: "success", icon: icon("入") },
    { key: "out", title: `${month} 外部流出`, subtitle: `折人民币 · 汇率 ${fx}`, value: fmtMoney(outExt), tone: "danger", icon: icon("出") },
    { key: "uncat", title: "待分类流水", subtitle: "点击到日记账处理", value: uncat, tone: uncat ? "warning" : "normal", icon: icon("?") },
    { key: "fs_open", title: "审批单未付", subtitle: "点击看未付审批单", value: unpaid, tone: unpaid ? "warning" : "normal", icon: icon("单") },
    { key: "pairs", title: "内部配对", subtitle: `未配对 ${data.meta.summary.unpaired ?? 0}`, value: `${data.meta.summary.pairs ?? 0} 对`, tone: "normal", icon: icon("⇄") },
  ];
  const columns: ProColumns<Row>[] = [
    { title: "账户", dataIndex: "name", width: 280, fixed: "left", render: (_, row) => <Typography.Text strong>{row.name}</Typography.Text> },
    { title: "类型", dataIndex: "kind", width: 80, render: (_, row) => <Tag bordered={false} color={KIND_COLOR[row.kind]}>{row.kind}</Tag> },
    { title: "币种", dataIndex: "cur", width: 70 },
    { title: "流水覆盖", width: 190, tooltip: "表头声明的查询区间优先；没有的按文件首末两笔；区间内没有行 = 该段无交易", render: (_, row) => { const cov = coverage[row.id]; return cov ? <span className="finance-board__stack">{cov.from} ~ {cov.to}<span className="finance-board__sub">{cov.src === "表头" ? "表头声明" : "按首末笔"}</span></span> : EMPTY; } },
    { title: "期初", dataIndex: "open", width: 140, align: "right", render: (_, row) => <FinMoney value={row.open} cur={row.cur} /> },
    { title: "外部流入", dataIndex: "in_ext", width: 140, align: "right", render: (_, row) => <FinMoney value={row.in_ext} cur={row.cur} /> },
    { title: "外部流出", dataIndex: "out_ext", width: 140, align: "right", render: (_, row) => <FinMoney value={row.out_ext} cur={row.cur} /> },
    { title: "内部净", width: 130, align: "right", render: (_, row) => <FinMoney value={(row.in_int ?? 0) + (row.out_int ?? 0)} cur={row.cur} /> },
    { title: "期末（算）", dataIndex: "close", width: 140, align: "right", render: (_, row) => <FinMoney value={row.close} cur={row.cur} /> },
    { title: "表中期末", dataIndex: "sheet_close", width: 140, align: "right", tooltip: "余额链链尾；与期末（算）差 > 1 元说明漏行或行序错", render: (_, row) => (row.sheet_close == null ? <Typography.Text type="secondary">无余额列</Typography.Text> : <FinMoney value={row.sheet_close} cur={row.cur} />) },
    { title: "行数", dataIndex: "n_lines", width: 80, align: "right", render: (_, row) => (row.n_lines ? <Button type="link" size="small" onClick={() => openJournal({ account: row.id })}>{row.n_lines}</Button> : 0) },
    { title: "待分类", dataIndex: "uncat", width: 80, align: "right", render: (_, row) => (row.uncat ? <Tag color="red" bordered={false}>{row.uncat}</Tag> : 0) },
  ];
  return (
    <FinanceBoardFrame
      title="账户总览（按月）"
      subtitle={`起点 ${data.meta.start} · 构建 ${data.meta.built} · 银行 / 平台导出 ${(data.meta.bank_files ?? []).length} 份`}
      toolbar={<>
        <ReportFacetSelect ariaLabel="月份" placeholder="月份" value={month} allowClear={false} showSearch={false} options={months.map((value) => ({ value, label: value }))} onChange={(value) => setMonth(String(value ?? months[months.length - 1]))} />
        <span className="finance-board__toolbar-actions"><Tooltip title={LOCKED_TIP}><Button disabled>导出 Excel</Button></Tooltip></span>
      </>}
      summary={<ManagementStatCards<string> ariaLabel="账户总览统计" className="finance-board__summary finance-board__summary--5" cards={cards} activeKey="" onCardClick={(key) => { if (key === "uncat") openJournal({ card: "uncat" }); if (key === "fs_open") openJournal({ card: "fs_open" }); }} />}
    >
      <BoardTable<Row> label="账户总览表格" rowKey="id" rows={rows} columns={columns} emptyTitle="暂无账户" emptyText="还没有导入任何现金流账户报表" pageSize={50} />
    </FinanceBoardFrame>
  );
}

/* ======================================================= 日记账 */
function JournalBoard({ data }: { data: CashSnapshot }) {
  const handoff = useMemo(() => readHandoff(), []);
  const [accounts, setAccounts] = useState<string[]>(handoff.account ? [handoff.account] : []);
  const [month, setMonth] = useState<string>("");
  const [cats, setCats] = useState<string[]>([]);
  const [flow, setFlow] = useState<"" | "in" | "out">("");
  const [stages, setStages] = useState<ReviewStage[]>([]);
  const [alertTypes, setAlertTypes] = useState<string[]>([]);
  const [search, setSearch] = useState({ field: "text", keyword: "" });
  const [card, setCard] = useState<ReviewCard>(handoff.card ?? "all");
  const [lineOpen, setLineOpen] = useState<CashLine>();
  const [approvalOpen, setApprovalOpen] = useState<FeishuApproval>();
  const [reviews, setReviews] = useState<Record<string, ReviewMark>>({});
  const [rejecting, setRejecting] = useState<{ line: CashLine; level: 1 | 2 }>();
  const [rejectReason, setRejectReason] = useState("");
  const [noting, setNoting] = useState<CashLine>();
  const [noteText, setNoteText] = useState("");
  const approvalsFile = useApprovals();
  const details = useMemo(() => approvalsFile.data?.items ?? {}, [approvalsFile.data]);
  const [columnKeys, setColumnKeys] = useState<string[]>(readJournalColumns);
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [messageApi, messageHolder] = message.useMessage();
  const reviewOf = (line: CashLine) => reviews[line.id] ?? baseReview(line);
  /* 初审：审批金额和流水金额有差额 → 必须先写差额说明（不限差额大小）；终审直接通过。 */
  const pass = (line: CashLine, level: 1 | 2, note?: string) => {
    const diff = amountDiff(line, approvalsOf(line));
    if (level === 1 && diff != null && diff !== 0 && note === undefined) {
      setNoteText(reviews[line.id]?.note ?? "");
      setNoting(line);
      return;
    }
    setReviews((current) => ({ ...current, [line.id]: { stage: level === 1 ? "ok1" : "ok2", note: note ?? current[line.id]?.note } }));
    void messageApi.success(`${level === 1 ? "初审" : "终审"}通过（${PREVIEW_ACTION_TIP}）`);
  };
  const confirmNote = () => {
    if (!noting || !noteText.trim()) return;
    pass(noting, 1, noteText.trim());
    setNoting(undefined);
    setNoteText("");
  };
  const confirmReject = () => {
    if (!rejecting || !rejectReason.trim()) return;
    setReviews((current) => ({ ...current, [rejecting.line.id]: { stage: rejecting.level === 1 ? "rej1" : "rej2", reason: rejectReason.trim(), note: current[rejecting.line.id]?.note } }));
    void messageApi.warning(rejecting.level === 1 ? "初审不通过，已记原因" : "终审不通过，已驳回到待初审");
    setRejecting(undefined);
    setRejectReason("");
  };
  const applyColumns = (keys: string[]) => {
    setColumnKeys(keys);
    writeUserPreference("anonymous", JOURNAL_COLUMN_PREF_KEY, JOURNAL_COLUMN_PREF_VERSION, keys);
    setColumnConfigOpen(false);
  };
  /* 飞书只读测试拉到、但不在本期审批单快照里的单（多是流水截止日之后的单）：已同意的并进「审批单未付」，点开能看凭证。 */
  const feishuAll = useMemo(() => {
    const known = new Set(data.feishu.map((item) => item.serial));
    const extra: FeishuApproval[] = Object.values(details).filter((d) => !known.has(d.serial) && d.status === "已同意" && d.amount != null)
      .map((d) => ({ serial: d.serial, kind: d.kind, status: d.status, start: d.start.slice(0, 10), end: d.end.slice(0, 10), applicant: "", reason: d.reason, amount: d.amount, cur: d.cur, pay: d.pay, payee: d.payee, bank: d.bank, last4: d.last4, items: d.items, rel: "", invoice: d.invoice, src: "飞书只读测试", cat: "", masked: false, paid: [], paid_sum: 0, cny: d.amount, state: "未付" }));
    return [...data.feishu, ...extra];
  }, [data, details]);
  const approvals = useMemo(() => new Map(feishuAll.map((item) => [item.serial, item])), [feishuAll]);
  const approvalsOf = (line: CashLine) => line.refs.map((ref) => viewOf(ref, approvals.get(ref), details[ref]));
  const accountMap = useMemo(() => new Map(data.accounts.map((item) => [item.id, item])), [data]);
  /* 异常落到流水上：有流水号的直接挂；审批单类挂到关联了该单的流水；余额不连续按 账户 + 日期 + 余额 找断点那条流水。
     落不到流水上的（剔除未命中、账户级提示）放表格上方提示条；没关联流水的审批单类在「审批单未付」卡片里。 */
  const alertIndex = useMemo(() => {
    const byLine = new Map<string, CashAlert[]>();
    const orphans: CashAlert[] = [];
    const push = (id: string, item: CashAlert) => byLine.set(id, [...(byLine.get(id) ?? []), item]);
    for (const item of toCashAlerts(data.anomalies)) {
      if (item.line) { push(item.line, item); continue; }
      if (item.serial) {
        const hits = data.lines.filter((line) => line.refs.includes(item.serial as string));
        hits.forEach((line) => push(line.id, item));
        if (!hits.length && !item.type.startsWith("审批单")) orphans.push(item);
        continue;
      }
      const hit = item.type === "余额不连续" ? data.lines.find((line) => line.acct === item.acct && line.date === item.date && line.bal != null && line.amt != null
        && Math.abs(line.bal - line.amt - (item.amt ?? NaN)) < 0.011) : undefined;
      if (hit) push(hit.id, { ...item, ref: hit.id, id: `${item.type}|${hit.id}` });
      else orphans.push(item);
    }
    return { byLine, orphans };
  }, [data]);
  const alertsOf = (line: CashLine) => alertIndex.byLine.get(line.id) ?? [];
  const realAlertsOf = (line: CashLine) => alertsOf(line).filter((item) => !item.hint);
  const alertTypeOptions = Array.from(new Set(data.lines.flatMap((line) => realAlertsOf(line).map((item) => item.type))))
    .map((value) => ({ value, label: alertShort(value), count: data.lines.filter((line) => realAlertsOf(line).some((item) => item.type === value)).length }));
  const base = data.lines.filter((line) => (accounts.length === 0 || accounts.includes(line.acct)) && (!month || line.m === month)
    && (cats.length === 0 || cats.includes(line.cat || "NONE"))
    && (!flow || (flow === "in" ? (line.amt ?? 0) > 0 : (line.amt ?? 0) < 0))
    && (stages.length === 0 || stages.includes(reviewOf(line).stage))
    && (alertTypes.length === 0 || realAlertsOf(line).some((item) => alertTypes.includes(item.type)))
    && (!search.keyword || (search.field === "party"
      ? (line.party ?? "").toLowerCase().includes(search.keyword.toLowerCase())
      : search.field === "ref"
        ? line.refs.some((ref) => ref.includes(search.keyword.trim()))
        : `${line.sum} ${line.memo} ${line.refs.join(" ")} ${line.id}`.toLowerCase().includes(search.keyword.toLowerCase()))));
  const counts: Record<ReviewCard, number> = {
    all: base.length,
    todo: base.filter((line) => isFirstPending(reviewOf(line).stage)).length,
    ok1: base.filter((line) => reviewOf(line).stage === "ok1").length,
    ok2: base.filter((line) => reviewOf(line).stage === "ok2").length,
    uncat: base.filter((line) => !line.cat && !line.parts).length,
    alert: base.filter((line) => realAlertsOf(line).length > 0).length,
    excluded: base.filter(isExcluded).length,
    fs_open: feishuAll.filter((item) => isOpenApproval(item, data)).length,
  };
  const rows = base.filter((line) => card === "all" || card === "fs_open" || (card === "todo" ? isFirstPending(reviewOf(line).stage) : card === "ok1" ? reviewOf(line).stage === "ok1" : card === "ok2" ? reviewOf(line).stage === "ok2" : card === "alert" ? realAlertsOf(line).length > 0 : card === "uncat" ? !line.cat && !line.parts : isExcluded(line)))
    .sort((a, b) => b.date.localeCompare(a.date) || (b.time ?? "").localeCompare(a.time ?? "") || (b.ord ?? 0) - (a.ord ?? 0));
  const cards: ManagementStatCardItem<ReviewCard>[] = [
    { key: "all", title: "全部流水", subtitle: "当前筛选", value: counts.all, tone: "normal", icon: icon("全") },
    { key: "todo", title: "待初审", subtitle: "含初审不通过 / 终审驳回", value: counts.todo, tone: counts.todo ? "warning" : "normal", icon: icon("初") },
    { key: "ok1", title: "待终审", subtitle: "初审已通过，等财务主管", value: counts.ok1, tone: "normal", icon: icon("终") },
    { key: "ok2", title: "已终审", subtitle: "可结账", value: counts.ok2, tone: "success", icon: icon("✓") },
    { key: "uncat", title: "待分类", subtitle: "规则没命中，需选类别", value: counts.uncat, tone: counts.uncat ? "danger" : "normal", icon: icon("?") },
    { key: "alert", title: "异常", subtitle: "未配对 / 明细不符 / 余额不连续等，都要处理", value: counts.alert, tone: counts.alert ? "danger" : "normal", icon: icon("!") },
    { key: "excluded", title: "已剔除", subtitle: "X01 非本公司", value: counts.excluded, tone: "normal", icon: icon("剔") },
    { key: "fs_open", title: "审批单未付", subtitle: `${data.meta.start} 起已批、未对上付款`, value: counts.fs_open, tone: counts.fs_open ? "warning" : "normal", icon: icon("单") },
  ];
  const catOptions = useMemo(() => data.cats.map((cat) => ({ value: cat.code, label: `${cat.code} ${cat.big}·${cat.name}` })), [data]);
  const openApprovalOptions = useMemo(() => feishuAll.filter((item) => isOpenApproval(item, data)).sort((a, b) => b.serial.localeCompare(a.serial))
    .map((item) => ({ value: item.serial, label: `${item.serial} ${item.masked ? "****" : fmtMoney(item.amount, item.cur)} ${(item.payee || "").slice(0, 10)} ${(item.masked ? "" : item.reason || "").slice(0, 16)}` })), [data, feishuAll]);
  const columnDefs: Record<string, ProColumns<CashLine>[]> = {
    date: [{ key: "date", title: "日期", dataIndex: "date", width: 116, fixed: "left", render: (_, row) => <span className="finance-board__stack">{row.date}<span className="finance-board__sub">{row.id.split(":").pop()}</span></span> }],
    acct: [{ key: "acct", title: "账户", dataIndex: "acct", width: 200, render: (_, row) => accountMap.get(row.acct)?.name ?? row.acct }],
    sum: [{ key: "sum", title: "摘要", dataIndex: "sum", width: 180, render: (_, row) => (row.masked ? <Typography.Text type="secondary">****</Typography.Text> : <Typography.Text ellipsis={{ tooltip: row.sum }} style={{ maxWidth: 164 }}>{row.sum || EMPTY}</Typography.Text>) }],
    memo: [{ key: "memo", title: "备注", dataIndex: "memo", width: 300, render: (_, row) => (row.masked ? <Typography.Text type="secondary">****</Typography.Text> : row.memo && row.memo !== row.sum ? <Typography.Text type="secondary" className="finance-board__fulltext">{row.memo}</Typography.Text> : EMPTY) }],
    party: [{ key: "party", title: "对方", dataIndex: "party", width: 200, render: (_, row) => (row.party ? <Typography.Text ellipsis={{ tooltip: row.party }} style={{ maxWidth: 184 }}>{row.party}</Typography.Text> : EMPTY) }],
    amt: [{ key: "amt", title: "金额", dataIndex: "amt", width: 130, align: "right", render: (_, row) => <FinMoney value={row.amt} cur={row.cur} masked={row.masked} /> }],
    cny: [{ key: "cny", title: "折人民币", dataIndex: "cny", width: 130, align: "right", render: (_, row) => (row.cur === "CNY" ? EMPTY : <FinMoney value={row.cny} masked={row.masked} />) }],
    bal: [{ key: "bal", title: "余额", dataIndex: "bal", width: 140, align: "right", render: (_, row) => <FinMoney value={row.bal ?? null} cur={row.cur} masked={row.masked} /> }],
    cat: [{ key: "cat", title: "类别", dataIndex: "cat", width: 230, tooltip: "直接在行上选类别；人工改过的优先于审批单与规则", render: (_, row) => (row.parts ? <Tag color="geekblue" bordered={false}>拆分 {row.parts.length} 行</Tag> : (
      <span className="finance-board__stack">
        <Tooltip title={LOCKED_TIP}><Select size="small" disabled style={{ width: 200 }} value={row.cat || undefined} placeholder={<Typography.Text type="danger">待分类</Typography.Text>} options={catOptions} /></Tooltip>
        <span className="finance-board__sub">来源：{row.cat_src || "—"}</span>
      </span>)) }],
    refs: [{ key: "refs", title: "审批单", dataIndex: "refs", width: 230, tooltip: "这笔付款对应哪张飞书审批单。自动：备注里有单号直接关联；金额 + 收款人 + 45 天内唯一候选自动关联。对不上的在这里输入或选未付审批单", render: (_, row) => (
      <span className="finance-board__stack">
        {row.refs.length > 0 && <Space size={4} wrap>{row.refs.map((ref) => { const item = approvals.get(ref); return <Tooltip key={ref} title={item ? `${item.kind} · ${item.state} · 点击看审批单` : "飞书里没找到"}><Tag bordered={false} className="finance-board__ref" color={item ? STATE_COLOR[item.state] ?? "blue" : "red"} onClick={() => item && setApprovalOpen(item)}>{ref}</Tag></Tooltip>; })}</Space>}
        <Tooltip title={LOCKED_TIP}><AutoComplete size="small" disabled style={{ width: 200 }} placeholder="关联审批单（输入或选未付单）" options={openApprovalOptions} /></Tooltip>
      </span>) }],
    alert: [{ key: "alert", title: "异常", width: 150, tooltip: "这笔流水上待处理的异常（灰色是数据提示，不算异常）；点详情看说明和处理方法", render: (_, row) => {
      const list = alertsOf(row);
      return list.length ? <Space size={4} wrap>{list.map((item) => <Tooltip key={item.id} title={item.msg}><Tag bordered={false} color={item.hint ? undefined : "red"}>{item.hint ? item.type : alertShort(item.type)}</Tag></Tooltip>)}</Space> : EMPTY;
    } }],
    review: [
      { key: "review_state", title: "审核状态", width: 150, fixed: "right", tooltip: "审批流转：待初审 → 财务专员 ✓ → 待终审 → 财务主管 ✓ → 已终审（按钮变灰）。✗ 须填原因；终审 ✗ 驳回到待初审。审核后再改类别 / 关联审批单 / 拆分 / 剔除会自动退回待初审", render: (_, row) => { const mark = reviewOf(row); return (
        <span className="finance-board__stack">
          <Tag color={REVIEW_TAG[mark.stage].color} bordered={false}>{REVIEW_TAG[mark.stage].text}</Tag>
          {mark.reason && <Typography.Text type="danger" className="finance-board__fulltext finance-board__sub">原因：{mark.reason}</Typography.Text>}
        </span>); } },
      { key: "review_act", title: "审核", width: 84, fixed: "right", tooltip: "轮到初审时是初审、轮到终审时是终审（看左边审核状态）；✓ 通过，✗ 不通过须填原因；已终审变灰", render: (_, row) => { const stage = reviewOf(row).stage; const level: 1 | 2 | undefined = isFirstPending(stage) ? 1 : stage === "ok1" ? 2 : undefined; const name = level === 1 ? "初审" : "终审"; return (
        <span className="finance-board__review-row">
          <Tooltip title={level ? `${name}通过` : "已终审"}><Button size="small" type="text" className="finance-board__review-pass" aria-label={`${name}通过`} icon={<CheckOutlined aria-hidden="true" />} disabled={!level} onClick={() => level && pass(row, level)} /></Tooltip>
          <Tooltip title={level ? `${name}不通过（填原因${level === 2 ? "，驳回到待初审" : ""}）` : "已终审"}><Button size="small" type="text" danger aria-label={`${name}不通过`} icon={<CloseOutlined aria-hidden="true" />} disabled={!level} onClick={() => level && setRejecting({ line: row, level })} /></Tooltip>
        </span>); } },
    ],
  };
  const lineColumns: ProColumns<CashLine>[] = [
    ...columnDefs.date,
    ...columnKeys.filter((key) => !JOURNAL_FIXED_KEYS.includes(key)).flatMap((key) => columnDefs[key] ?? []),
    ...columnDefs.review,
    { key: "actions", title: "操作", width: 72, fixed: "right", render: (_, row) => <Space size={0}><Button type="link" size="small" onClick={() => setLineOpen(row)}>详情</Button></Space> },
  ];
  const approvalColumns: ProColumns<FeishuApproval>[] = [
    { title: "申请编号", dataIndex: "serial", width: 150, fixed: "left", render: (_, row) => <span className="finance-board__stack"><Button type="link" size="small" style={{ padding: 0 }} onClick={() => setApprovalOpen(row)}>{row.serial}</Button><span className="finance-board__sub">{row.kind}</span></span> },
    { title: "状态", dataIndex: "state", width: 100, render: (_, row) => <Tag bordered={false} color={STATE_COLOR[row.state]}>{row.state}</Tag> },
    { title: "发起 / 完成", width: 140, render: (_, row) => <span className="finance-board__stack">{row.start}<span className="finance-board__sub">{row.end || EMPTY}{row.days != null ? ` · ${row.days} 天` : ""}</span></span> },
    { title: "收款人", width: 200, render: (_, row) => <span className="finance-board__stack">{row.payee || EMPTY}<span className="finance-board__sub">{row.bank}{row.last4 ? ` …${row.last4}` : ""}</span></span> },
    { title: "事由", dataIndex: "reason", width: 320, ellipsis: true, render: (_, row) => (row.masked ? "****" : row.reason) },
    { title: "金额", dataIndex: "amount", width: 140, align: "right", render: (_, row) => <FinMoney value={row.amount} cur={row.cur} masked={row.masked} /> },
    { title: "已付（¥）", dataIndex: "paid_sum", width: 140, align: "right", render: (_, row) => <FinMoney value={row.paid_sum} masked={row.masked} /> },
  ];
  const months = data.meta.months;
  /* 按审批单号搜不到流水时，说明这张单在哪：还没关联流水的已批单在「审批单未付」里。 */
  const refHint = (() => {
    const keyword = search.keyword.trim();
    if (!keyword || rows.length || !/^\d{6,}$/.test(keyword)) return "";
    const hits = feishuAll.filter((item) => item.serial.includes(keyword));
    if (!hits.length) return `没有流水，本地也没找到审批单 ${keyword}（可能还没从飞书同步过来）`;
    const item = hits[0];
    const where = isOpenApproval(item, data) ? "在上方「审批单未付」卡片里，点开能看审批单和凭证" : `飞书状态：${item.status || "—"}，付款状态：${item.state}`;
    return `审批单 ${item.serial}（${item.kind} ${item.masked ? "" : fmtMoney(item.amount, item.cur)} ${item.payee}）还没有关联任何流水，${where}${hits.length > 1 ? `；另有 ${hits.length - 1} 张单号相近` : ""}`;
  })();
  return (
    <FinanceBoardFrame
      title="日记账"
      subtitle="按银行明细顺序；流水 id 后 6 位是内容指纹，重复导入自动去重；类别来源：人工 > 审批单 > 规则"
      toolbar={<>
        <ReportFacetSelect mode="multiple" ariaLabel="账户" placeholder="账户" unit="个" value={accounts} options={data.accounts.map((item) => ({ value: item.id, label: accountLabel(item), count: data.lines.filter((line) => line.acct === item.id).length }))} onChange={(value) => setAccounts((value as string[] | undefined) ?? [])} />
        <ReportFacetSelect ariaLabel="月份" placeholder="全部月份" value={month || undefined} options={months.map((value) => ({ value, label: value }))} onChange={(value) => setMonth(value ? String(value) : "")} />
        <ReportFacetSelect ariaLabel="收入 / 支出" placeholder="收入 / 支出" triggerWidth={150} value={flow || undefined} options={[{ value: "in", label: "收入", count: data.lines.filter((line) => (line.amt ?? 0) > 0).length }, { value: "out", label: "支出", count: data.lines.filter((line) => (line.amt ?? 0) < 0).length }]} onChange={(value) => setFlow(value === "in" || value === "out" ? value : "")} />
        <ReportFacetSelect mode="multiple" ariaLabel="类别" placeholder="类别" unit="类" popupWidth={420} value={cats} options={[{ value: "NONE", label: "待分类" }, ...data.cats.map((cat) => ({ value: cat.code, label: `${cat.code} ${cat.big}·${cat.name}`, count: data.lines.filter((line) => line.cat === cat.code).length }))]} onChange={(value) => setCats((value as string[] | undefined) ?? [])} />
        <ReportFacetSelect mode="multiple" ariaLabel="审核状态" placeholder="审核状态" unit="项" value={stages} options={REVIEW_STAGE_OPTIONS.map((option) => ({ ...option, count: data.lines.filter((line) => reviewOf(line).stage === option.value).length }))} onChange={(value) => setStages((value as ReviewStage[] | undefined) ?? [])} />
        <ReportFacetSelect mode="multiple" ariaLabel="异常" placeholder="异常" unit="类" triggerWidth={150} value={alertTypes} options={alertTypeOptions} onChange={(value) => setAlertTypes((value as string[] | undefined) ?? [])} />
        <CommittedSearch className="finance-board__search fin-cash-flow__search" typeAriaLabel="搜索类型" typeOptions={[{ value: "text", label: "摘要备注" }, { value: "party", label: "收款人" }, { value: "ref", label: "审批单号" }]} typeValue={search.field} inputAriaLabel="搜索流水" inputPlaceholder="输入后回车" inputValue={search.keyword} onCommit={({ searchField, keyword }) => setSearch({ field: searchField, keyword })} />
        <ResetButton onClick={() => { setAccounts([]); setMonth(""); setFlow(""); setCats([]); setStages([]); setAlertTypes([]); setSearch({ field: "text", keyword: "" }); setCard("all"); }} />
        <Space className="finance-board__toolbar-actions" size={8}><Button type="primary" onClick={() => setImportOpen(true)}>流水导入</Button><Tooltip title={LOCKED_TIP}><Space><Button disabled>批量操作</Button><Button disabled>导出 Excel</Button></Space></Tooltip><Button aria-label="列配置" icon={<SettingOutlined aria-hidden="true" />} onClick={() => setColumnConfigOpen(true)} /></Space>
      </>}
      summary={<ManagementStatCards<ReviewCard> ariaLabel="日记账统计" className="finance-board__summary fin-cash-flow__summary--8" cards={cards} activeKey={card} onCardClick={(key) => setCard(card === key ? "all" : key)} />}
    >
      {alertIndex.orphans.length > 0 && (
        <Alert className="fin-cash-flow__orphans" type="warning" showIcon
          message={`${alertIndex.orphans.filter((item) => !item.hint).length} 条异常找不到对应流水${alertIndex.orphans.some((item) => item.hint) ? `，另有 ${alertIndex.orphans.filter((item) => item.hint).length} 条数据提示` : ""}`}
          description={<ul>{alertIndex.orphans.map((item) => <li key={item.id}><Tag bordered={false} color={item.hint ? undefined : "red"}>{item.hint ? item.type : alertShort(item.type)}</Tag>{item.date} · {accountMap.get(item.acct)?.name ?? (item.acct || EMPTY)} · {item.msg}{!item.hint && ALERT_GUIDE[item.type] ? <Typography.Text type="secondary">（处理：{ALERT_GUIDE[item.type].guide}）</Typography.Text> : null}</li>)}</ul>} />
      )}
      {card === "fs_open"
        ? <BoardTable<FeishuApproval> label="审批单未付表格" rowKey="serial" rows={feishuAll.filter((item) => isOpenApproval(item, data)).sort((a, b) => b.serial.localeCompare(a.serial))} columns={approvalColumns} emptyTitle="没有未付审批单" emptyText="飞书已批的单都已对上付款流水" pageSize={30} />
        : <BoardTable<CashLine> label="日记账表格" rowKey="id" rows={rows} columns={lineColumns} emptyTitle={refHint ? "没有对应的流水" : "暂无流水"} emptyText={refHint || "当前筛选下没有流水"} />}
      {messageHolder}
      <RuntimeColumnConfigDrawer open={columnConfigOpen} groups={JOURNAL_COLUMN_GROUPS} fixedKeys={JOURNAL_FIXED_KEYS} defaultKeys={JOURNAL_DEFAULT_KEYS} appliedKeys={columnKeys} onApply={applyColumns} onClose={() => setColumnConfigOpen(false)} onSaveTemplate={() => void messageApi.info("列模板暂未开放；当前列配置仅保存在本浏览器")} />
      <Modal open={Boolean(rejecting)} title={rejecting?.level === 2 ? "终审不通过 · 驳回到待初审" : "初审不通过"} okText="确定不通过" okButtonProps={{ danger: true, disabled: !rejectReason.trim() }} cancelText="取消" onOk={confirmReject} onCancel={() => { setRejecting(undefined); setRejectReason(""); }} destroyOnHidden>
        {rejecting && <Typography.Paragraph type="secondary">{rejecting.line.date} · {accountMap.get(rejecting.line.acct)?.name ?? rejecting.line.acct} · {rejecting.line.masked ? "****" : fmtMoney(rejecting.line.amt, rejecting.line.cur)}</Typography.Paragraph>}
        <Input.TextArea autoFocus rows={3} maxLength={200} showCount placeholder="必填：不通过的原因（会显示在审核状态下，财务专员据此修改）" value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} />
      </Modal>
      <Modal open={Boolean(noting)} title="初审通过 · 写差额说明" okText="初审通过" okButtonProps={{ disabled: !noteText.trim() }} cancelText="取消" onOk={confirmNote} onCancel={() => { setNoting(undefined); setNoteText(""); }} destroyOnHidden>
        {noting && <Typography.Paragraph>审批单金额和这笔流水对不上：<Typography.Text type="danger">差额 {fmtMoney(amountDiff(noting, approvalsOf(noting)), noting.cur)}</Typography.Text>（审批单合计 − 流水金额）。写清楚原因，终审会看到。</Typography.Paragraph>}
        <Input.TextArea autoFocus rows={3} placeholder="必填：为什么有差额（例如：手续费由我方承担、分两笔付、汇率差……）" value={noteText} onChange={(event) => setNoteText(event.target.value)} />
      </Modal>
      <LineDrawer line={lineOpen} review={lineOpen ? reviewOf(lineOpen) : undefined} data={data} details={details} approvalsOf={approvalsOf} alerts={lineOpen ? alertsOf(lineOpen) : []} onClose={() => setLineOpen(undefined)} onOpenApproval={setApprovalOpen}
        onPass={(line) => pass(line, 2)} onReject={(line) => setRejecting({ line, level: 2 })} />
      <ApprovalDrawer item={approvalOpen} data={data} details={details} onClose={() => setApprovalOpen(undefined)} />
      <ImportDrawer open={importOpen} onClose={() => setImportOpen(false)} />
    </FinanceBoardFrame>
  );
}

/** 资金流水下的左侧菜单页（2026-11-02 Rocky：做成资金流水的下一级菜单，UI 与正式系统一致；11-04 去掉「异常」页）。 */
function FinanceCashFlowPage({ page, view }: { page: NavigationPage; view: CashFlowView }) {
  const snapshot = useCashSnapshot();
  const data = snapshot.data;
  const fallbackTitle = { accounts: "账户总览（按月）", journal: "日记账", stock: "备货资金" }[view];
  const stock = useStock(view === "stock");
  return (
    <PageShell page={page} headerActions={view === "stock" ? <CashStockHelp data={stock.data} /> : undefined}>
      {view === "stock" ? <CashStockBoard /> : !data ? (
        <FinanceBoardFrame title={fallbackTitle} loading={snapshot.isPending}>
          <EmptyState
            title={snapshot.error ? "本地预览数据未就绪" : "加载中"}
            description={snapshot.error ? (snapshot.error as Error).message : "正在读取本地预览数据"}
          />
        </FinanceBoardFrame>
      ) : view === "accounts" ? <AccountsBoard data={data} />
        : <JournalBoard data={data} />}
    </PageShell>
  );
}

export default FinanceCashFlowPage;

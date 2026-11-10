/**
 * 回款对账 · 对账表：选一期或几期（账单日），每店一行；回款状态 + 初审（财务专员）→ 终审（财务主管）。
 * 人工只做两件事：确认到账（= 初审通过）、跟进打款异常（写跟进记录）。页面上不显示审核人名字。
 * 数据全部来自 /api/finance/payout-recon（Rocky 2026-11-10），操作写后端后整页刷新。
 */
import { CheckOutlined, CloseOutlined, EditOutlined, SettingOutlined } from "@ant-design/icons";
import { Button, Input, Modal, Space, Table, Tag, Tooltip, Typography, message } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import { useState, type ReactNode } from "react";
import { MoneyCell } from "@/components/report-table/cells";
import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import ResetButton from "@/components/report-table/ResetButton";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import FinanceBoardFrame from "@/pages/finance/FinanceBoardFrame";
import ReportFacetSelect from "@/shared/report-filters";
import BoardTable from "./BoardTable";
import FollowModal from "./FollowModal";
import ReconBatch from "./ReconBatch";
import type { PayState, ReconRow, ReviewStage } from "./reconApi";
import { RECON_COLUMN_GROUPS, RECON_DEFAULT_KEYS, RECON_FIXED_KEYS, readReconColumns, writeReconColumns } from "./reconColumns";
import { PAY_STATE, REVIEW_TAG, isFirstPending, isMatched, n2, timeText } from "./reconModel";

type CardKey = "all" | "paid" | "anomaly" | "todo" | "ok1";

const EMPTY = "—";
const icon = (text: string) => <span className="management-stat-card__mark">{text}</span>;
const usd = (value: number | null | undefined, strong?: boolean) =>
  strong ? <Typography.Text strong><MoneyCell value={value} /></Typography.Text> : <MoneyCell value={value} />;

export interface ReconBoardProps {
  actions: ReactNode;
  subtitle: ReactNode;
  rows: ReconRow[];
  payDates: string[];
  /** 选中的账单日（期次多选，Rocky 11-09）：默认最新一期；不选 / 全选 = 全部期 */
  picked: string[];
  onPicked: (value: string[]) => void;
  onPass: (row: ReconRow, level: 1 | 2) => void;
  onReject: (row: ReconRow, reason: string) => void;
  onFollowUp: (row: ReconRow, values: { content: string; caseNo?: string; nextAt?: string }) => Promise<void>;
  onBatchDone: () => void;
  onOpen: (row: ReconRow) => void;
}

function ReconBoard({ actions, subtitle, rows: allRows, payDates, picked, onPicked, onPass, onReject, onFollowUp, onBatchDone, onOpen }: ReconBoardProps) {
  const [messageApi, messageHolder] = message.useMessage();
  const [columnKeys, setColumnKeys] = useState<string[]>(readReconColumns);
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [stores, setStores] = useState<string[]>([]);
  const [states, setStates] = useState<PayState[]>([]);
  const [stages, setStages] = useState<ReviewStage[]>([]);
  const [card, setCard] = useState<CardKey>("all");
  const [rejecting, setRejecting] = useState<ReconRow>();
  const [following, setFollowing] = useState<ReconRow>();
  // 打款异常（未到账、金额不符、账单作废）都要财务专员跟进（Rocky 11-09）。
  const needsFollow = (row: ReconRow) => row.anomaly;
  const [text, setText] = useState("");

  const latest = payDates[0] ?? "";
  const chosen = picked.length ? new Set(picked) : null;
  const period = allRows.filter((row) => !chosen || chosen.has(row.payDate));
  const pickedDays = Array.from(new Set(period.map((row) => row.payDate))).sort();
  const rangeText = !pickedDays.length ? EMPTY : pickedDays.length === 1 ? pickedDays[0] : `${pickedDays[0]} ~ ${pickedDays.at(-1)}`;
  const passes = (row: ReconRow) =>
      (!stores.length || stores.includes(row.sid)) &&
      (!states.length || states.includes(row.state)) &&
      (!stages.length || (isMatched(row) && stages.includes(row.stage)));
  const base = period.filter(passes);
  // 打款异常不分期：所有历史期次里未到账、金额不符的都在这里跟进 Case。
  const anomalies = allRows.filter((row) => row.anomaly && passes(row));
  const inCard = (row: ReconRow, key: CardKey) =>
    key === "all" || key === "anomaly" ||
    (key === "paid" ? isMatched(row) : key === "todo" ? isMatched(row) && isFirstPending(row.stage) : isMatched(row) && row.stage === "ok1");
  const rows = card === "anomaly" ? anomalies : base.filter((row) => inCard(row, card));
  const sum = (list: ReconRow[], pick: (row: ReconRow) => number | null) => list.reduce((total, row) => total + (pick(row) ?? 0), 0);
  const count = (key: CardKey) => (key === "anomaly" ? anomalies.length : base.filter((row) => inCard(row, key)).length);
  const cards: ManagementStatCardItem<CardKey>[] = [
    { key: "all", title: "应付合计", subtitle: `${new Set(base.map((row) => row.payDate)).size} 期 · ${new Set(base.map((row) => row.sid)).size} 个店铺 · 账单日 ${rangeText}`, value: `$${n2(sum(base.filter((row) => row.state !== "voided"), (row) => row.payable))}`, tone: "normal", icon: icon("$") },
    { key: "paid", title: "已打款", subtitle: `到账 $${n2(sum(base, (row) => row.arrived))}`, value: count("paid"), tone: "success", icon: icon("✓") },
    { key: "anomaly", title: "打款异常", subtitle: "全部期次：账单日过 7 天未到账、到账金额不符、账单作废；点开跟进 Case", value: count("anomaly"), tone: count("anomaly") ? "danger" : "normal", icon: icon("!") },
    { key: "todo", title: "待初审", subtitle: "已配上到账，等财务专员确认到账", value: count("todo"), tone: count("todo") ? "warning" : "normal", icon: icon("初") },
    { key: "ok1", title: "待终审", subtitle: "初审已通过，等财务主管", value: count("ok1"), tone: "normal", icon: icon("终") },
  ];

  const columns: ProColumns<ReconRow>[] = [
    { key: "code", title: "店铺", dataIndex: "code", width: 90, fixed: "left", render: (_, row) => <Tag bordered={false}>{row.code}</Tag> },
    { key: "payDate", title: "账单日", dataIndex: "payDate", width: 110 },
    { key: "org", title: "收款机构", width: 100, ellipsis: true, render: (_, row) => row.org || <Typography.Text type="secondary">未匹配</Typography.Text> },
    { key: "payee", title: "收款账户", dataIndex: "payee", width: 220, ellipsis: true, tooltip: "派安盈是付款邮箱，PingPong 是公司名称", render: (_, row) => row.payee || <Typography.Text type="secondary">未匹配</Typography.Text> },
    { key: "account", title: "入账账户（日记账）", width: 180, ellipsis: true, render: (_, row) => row.accountName || <Typography.Text type="secondary">未匹配</Typography.Text> },
    { key: "cycle", title: "账期", width: 200, tooltip: "这一期账单覆盖的交易日期（领星没给账期时按最早 / 最晚交易日期）", render: (_, row) => (row.cycleFrom ? `${row.cycleFrom} ~ ${row.cycleTo}` : EMPTY) },
    { key: "payable", title: "应付", dataIndex: "payable", width: 120, align: "right", render: (_, row) => usd(row.payable, true) },
    { key: "arrived", title: "到账", dataIndex: "arrived", width: 120, align: "right", render: (_, row) => (row.arrived == null ? <Typography.Text type="secondary">{EMPTY}</Typography.Text> : usd(row.arrived)) },
    { key: "diff", title: "差额", dataIndex: "diff", width: 110, align: "right", tooltip: "到账 − 应付；±0.01 以内算对上", render: (_, row) => (row.diff == null ? EMPTY : row.state === "mismatch" ? <Typography.Text type="danger"><MoneyCell value={row.diff} /></Typography.Text> : <Tag color="green" bordered={false}>0.00</Tag>) },
    { key: "arrivedAt", title: "到账日期", dataIndex: "arrivedAt", width: 110, render: (_, row) => row.arrivedAt || EMPTY },
    { key: "method", title: "配对方式", width: 110, tooltip: "自动 = 按规则配上；手动 = 财务在详情里配；合并打款显示几期一起", render: (_, row) => (row.matchMethod ? <Tag bordered={false} color={row.matchMethod === "auto" ? "blue" : "purple"}>{row.matchMethod === "auto" ? "自动" : "手动"}{row.matchSize > 1 ? ` · 合并 ${row.matchSize} 期` : ""}</Tag> : EMPTY) },
    {
      key: "state", title: "回款状态", dataIndex: "state", width: 150,
      render: (_, row) => (
        <Tooltip title={PAY_STATE[row.state].tip}><Tag color={PAY_STATE[row.state].color} bordered={false}>{PAY_STATE[row.state].text}</Tag></Tooltip>
      ),
    },
    { key: "caseNo", title: "Case 编号", width: 120, render: (_, row) => row.latestFollow?.case_no || EMPTY },
    { key: "nextAt", title: "下次跟进", width: 110, render: (_, row) => row.latestFollow?.next_follow_date || EMPTY },
    {
      key: "follow", title: "最新跟进", width: 240,
      tooltip: "打款异常的要跟进；点铅笔直接编辑，每次保存追加一条，详情里看全部记录",
      render: (_, row) => {
        const latest = row.latestFollow;
        const editable = needsFollow(row);
        return (
          <span className="fin-payout-recon__follow-cell">
            {latest ? (
              <Tooltip placement="topLeft" title={<div className="fin-payout-recon__follow-tip">{latest.content}<br />{timeText(latest.created_at)}</div>}>
                <span className="fin-payout-recon__follow-text" tabIndex={0}>{latest.content.replace(/\s+/g, " ")}</span>
              </Tooltip>
            ) : (
              <Typography.Text type={editable ? "warning" : "secondary"}>{editable ? "待跟进" : EMPTY}</Typography.Text>
            )}
            {editable && <Button size="small" type="text" aria-label="编辑跟进" icon={<EditOutlined aria-hidden="true" />} onClick={() => setFollowing(row)} />}
          </span>
        );
      },
    },
    {
      key: "review_state", title: "审核状态", width: 150, fixed: "right",
      tooltip: "审批流转：待初审 → 财务专员 ✓ 确认到账 → 待终审 → 财务主管 ✓ / ✗ → 已终审（按钮变灰）。初审点错了请终审驳回；终审 ✗ 须填原因，驳回到待初审。没配上到账的不审核。",
      render: (_, row) => {
        if (!isMatched(row)) return <Typography.Text type="secondary">{row.state === "no_pay" ? "不需审核" : "等配上到账"}</Typography.Text>;
        return (
          <span className="finance-board__stack">
            <Tag color={REVIEW_TAG[row.stage].color} bordered={false}>{REVIEW_TAG[row.stage].text}</Tag>
            {row.stageReason && <Typography.Text type="danger" className="finance-board__sub">原因：{row.stageReason}</Typography.Text>}
          </span>
        );
      },
    },
    {
      key: "review_act", title: "审核", width: 84, fixed: "right",
      tooltip: "轮到初审时是初审（= 确认到账），轮到终审时是终审（看左边审核状态）；✓ 通过；终审还有 ✗ 驳回（须填原因）；已终审变灰",
      render: (_, row) => {
        if (!isMatched(row)) return null;
        const stage = row.stage;
        const level: 1 | 2 | undefined = isFirstPending(stage) ? 1 : stage === "ok1" ? 2 : undefined;
        const name = level === 1 ? "初审（确认到账）" : "终审";
        return (
          <span className="finance-board__review-row">
            <Tooltip title={level ? `${name}通过` : "已终审"}>
              <Button size="small" type="text" className="finance-board__review-pass" aria-label={`${name}通过`} icon={<CheckOutlined aria-hidden="true" />} disabled={!level} onClick={() => level && onPass(row, level)} />
            </Tooltip>
            {level === 2 && (
              <Tooltip title="终审不通过（填原因，驳回到待初审）">
                <Button size="small" type="text" danger aria-label="终审不通过" icon={<CloseOutlined aria-hidden="true" />} onClick={() => setRejecting(row)} />
              </Tooltip>
            )}
          </span>
        );
      },
    },
    { key: "op", title: "操作", width: 72, fixed: "right", render: (_, row) => <Button type="link" size="small" onClick={() => onOpen(row)}>详情</Button> },
  ];

  const byKey = new Map(columns.map((column) => [String(column.key), column]));
  const shownColumns = [...columnKeys.flatMap((key) => (key === "review" ? ["review_state", "review_act"] : [key])), "op"]
    .map((key) => byKey.get(key))
    .filter((column): column is ProColumns<ReconRow> => Boolean(column));
  const visibleKeys = new Set(rows.map((row) => row.key));
  const selectedRows = rows.filter((row) => selectedKeys.includes(row.key));
  const totalPayable = sum(rows.filter((row) => row.state !== "voided"), (row) => row.payable);
  const totalArrived = sum(rows, (row) => row.arrived);
  const totalDiff = sum(rows, (row) => row.diff);
  const totals: Record<string, ReactNode> = {
    code: <Typography.Text strong>合计</Typography.Text>,
    payDate: <Typography.Text type="secondary">{rows.length} 行 · {new Set(rows.map((row) => row.payDate)).size} 期</Typography.Text>,
    payable: usd(totalPayable, true),
    arrived: usd(totalArrived, true),
    diff: Math.abs(totalDiff) > 0.005 ? <Typography.Text type="danger" strong><MoneyCell value={totalDiff} /></Typography.Text> : <Tag color="green" bordered={false}>0.00</Tag>,
  };
  const applyColumns = (keys: string[]) => { setColumnKeys(keys); writeReconColumns(keys); setColumnConfigOpen(false); };

  const submitText = () => {
    const value = text.trim();
    if (!value || !rejecting) return;
    onReject(rejecting, value);
    setRejecting(undefined);
    setText("");
  };

  return (
    <FinanceBoardFrame
      title="回款对账"
      subtitle={subtitle}
      toolbar={<>
        <ReportFacetSelect mode="multiple" ariaLabel="账单日" placeholder="全部期" unit="期" value={picked} showSearch={false}
          options={payDates.map((value) => ({ value, label: value === latest ? `${value}（最新一期）` : value, count: allRows.filter((row) => row.payDate === value).length }))}
          onChange={(value) => onPicked((value as string[] | undefined) ?? [])} />
        <ReportFacetSelect mode="multiple" ariaLabel="店铺" placeholder="店铺" unit="家" value={stores}
          options={Array.from(new Map(period.map((row) => [row.sid, row.code]))).map(([value, label]) => ({ value, label }))}
          onChange={(value) => setStores((value as string[] | undefined) ?? [])} />
        <ReportFacetSelect mode="multiple" ariaLabel="回款状态" placeholder="回款状态" unit="种" value={states}
          options={(Object.keys(PAY_STATE) as PayState[]).map((value) => ({ value, label: PAY_STATE[value].text, count: period.filter((row) => row.state === value).length }))}
          onChange={(value) => setStates((value as PayState[] | undefined) ?? [])} />
        <ReportFacetSelect mode="multiple" ariaLabel="审核状态" placeholder="审核状态" unit="项" value={stages}
          options={(Object.keys(REVIEW_TAG) as ReviewStage[]).map((value) => ({ value, label: REVIEW_TAG[value].text, count: period.filter((row) => isMatched(row) && row.stage === value).length }))}
          onChange={(value) => setStages((value as ReviewStage[] | undefined) ?? [])} />
        <ResetButton onClick={() => { onPicked(latest ? [latest] : []); setStores([]); setStates([]); setStages([]); setCard("all"); setSelectedKeys([]); }} />
        <Space className="finance-board__toolbar-actions" size={8}>
          {actions}
          <ReconBatch rows={rows} selected={selectedRows} onDone={() => { setSelectedKeys([]); onBatchDone(); }} />
          <Button aria-label="列配置" icon={<SettingOutlined aria-hidden="true" />} onClick={() => setColumnConfigOpen(true)} />
        </Space>
      </>}
      summary={<ManagementStatCards<CardKey> ariaLabel="回款对账统计" className="finance-board__summary finance-board__summary--5" cards={cards} activeKey={card} onCardClick={(key) => setCard(card === key ? "all" : key)} />}
    >
      <BoardTable<ReconRow> label="回款对账" resizeKey="finance-payout-recon:recon" rowKey="key" rows={rows} columns={shownColumns} onRow={onOpen}
        totals={totals}
        rowSelection={{ fixed: "left", columnWidth: 48, selectedRowKeys: selectedKeys.filter((key) => visibleKeys.has(key)), preserveSelectedRowKeys: true, onChange: (next) => setSelectedKeys(next.map(String)), selections: [Table.SELECTION_ALL, Table.SELECTION_INVERT, Table.SELECTION_NONE] }} emptyTitle={card === "anomaly" ? "没有打款异常" : "这段时间没有账单"} emptyText={card === "anomaly" ? "所有期次都已到账且金额对得上" : "换几期账单日（全选 = 全部期）或清掉筛选"} />
      <Modal
        open={Boolean(rejecting)}
        title={rejecting ? `终审不通过 · ${rejecting.code} · ${rejecting.payDate}` : ""}
        okText="确定驳回"
        okButtonProps={{ danger: true, disabled: !text.trim() }}
        cancelText="取消"
        onOk={submitText}
        onCancel={() => { setRejecting(undefined); setText(""); }}
        destroyOnHidden
      >
        {rejecting && <Typography.Paragraph type="secondary">应付 ${n2(rejecting.payable)}{rejecting.arrived != null ? ` · 到账 $${n2(rejecting.arrived)}` : ""}</Typography.Paragraph>}
        <Input.TextArea autoFocus rows={3} maxLength={300} showCount value={text} onChange={(event) => setText(event.target.value)} placeholder="必填：驳回原因（显示在审核状态下，财务专员据此处理）" />
      </Modal>
      {messageHolder}
      <RuntimeColumnConfigDrawer open={columnConfigOpen} groups={RECON_COLUMN_GROUPS} fixedKeys={RECON_FIXED_KEYS} defaultKeys={RECON_DEFAULT_KEYS} appliedKeys={columnKeys} onApply={applyColumns} onClose={() => setColumnConfigOpen(false)} onSaveTemplate={() => void messageApi.info("列模板暂未开放；当前列配置只保存在本浏览器")} />
      <FollowModal row={following} onClose={() => setFollowing(undefined)}
        onSubmit={async (values) => { if (following) await onFollowUp(following, values); setFollowing(undefined); }} />
    </FinanceBoardFrame>
  );
}

export default ReconBoard;

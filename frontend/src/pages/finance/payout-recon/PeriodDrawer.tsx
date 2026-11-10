/**
 * 回款对账 · 一期详情（照日记账详情）：账单字段 → 配对的到账（手动配对 / 撤销配对）→ 按金额类型小计 → 跟进记录 → 审核与配对记录；
 * 底部终审通过 / 终审不通过。页面上不显示审核人名字。
 */
import { CheckOutlined, CloseOutlined } from "@ant-design/icons";
import { Alert, Button, Checkbox, Descriptions, Divider, Drawer, Empty, Input, Modal, Space, Table, Tag, Timeline, Tooltip, Typography, message } from "antd";
import { useState } from "react";
import { MoneyCell } from "@/components/report-table/cells";
import { createMatch, reconErrorText, undoMatch, useCandidateLines, usePeriodDetail, type ApiLine, type ReconRow } from "./reconApi";
import { PAY_STATE, REVIEW_TAG, VOIDED_ARRIVAL_TEXT, isFirstPending, isMatched, n2, timeText } from "./reconModel";

const KIND_TEXT: Record<string, string> = {
  review1_pass: "确认到账（初审通过）",
  review2_pass: "终审通过",
  review2_reject: "终审驳回",
  reset: "撤销配对后回到待初审",
};

export interface PeriodDrawerProps {
  row?: ReconRow;
  /** 同一店铺还没配上到账的其他期次（合并打款时一起选） */
  openRows: ReconRow[];
  onPass: (row: ReconRow) => void;
  onReject: (row: ReconRow, reason: string) => void;
  onChanged: () => void;
  onClose: () => void;
}

function MatchModal({ row, openRows, onClose, onDone }: { row: ReconRow; openRows: ReconRow[]; onClose: () => void; onDone: () => void }) {
  const [messageApi, holder] = message.useMessage();
  const lines = useCandidateLines(row.sid, true);
  const [lineUid, setLineUid] = useState<string>();
  const [extra, setExtra] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const others = openRows.filter((item) => item.sid === row.sid && item.key !== row.key);
  const chosen = [row, ...others.filter((item) => extra.includes(item.key))];
  const picked = lines.data?.items.find((line) => line.line_uid === lineUid);
  const payable = chosen.reduce((total, item) => total + item.payable, 0);
  const submit = async () => {
    if (!lineUid) return;
    setBusy(true);
    try {
      await createMatch(lineUid, chosen, note.trim());
      void messageApi.success(`已配对 ${chosen.length} 期`);
      onDone();
    } catch (error) {
      void messageApi.error(reconErrorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal open width={860} title={`手动配对 · ${row.code} · 账单日 ${row.payDate}`} okText="确定配对" cancelText="取消" confirmLoading={busy}
      okButtonProps={{ disabled: !lineUid }} onOk={() => void submit()} onCancel={onClose} destroyOnHidden>
      {holder}
      <Typography.Paragraph type="secondary">选日记账里的一笔到账（这家店的收款账户、10 月起的收入）。几期合并打款的，在下面把其他期一起勾上。金额可以不等，配上后显示「金额不符」要跟进。</Typography.Paragraph>
      <Table<ApiLine>
        size="small"
        rowKey="line_uid"
        loading={lines.isPending}
        dataSource={lines.data?.items ?? []}
        pagination={{ pageSize: 8 }}
        rowSelection={{ type: "radio", selectedRowKeys: lineUid ? [lineUid] : [], onChange: (keys) => setLineUid(String(keys[0])), getCheckboxProps: (line) => ({ disabled: line.matched }) }}
        columns={[
          { title: "到账日期", dataIndex: "business_date", width: 110 },
          { title: "入账账户", dataIndex: "account_name", width: 180, ellipsis: true },
          { title: "金额", dataIndex: "amount", width: 120, align: "right", render: (_, line) => <MoneyCell value={Number(line.amount)} /> },
          { title: "付款方 / 摘要", key: "text", ellipsis: true, render: (_, line) => `${line.counterparty_name} ${line.description}`.trim() || "—" },
          { title: "状态", key: "matched", width: 140, render: (_, line) => (line.matched ? <Tag bordered={false}>已配对</Tag> : line.journal_hint
            ? <Tooltip title="日记账里这笔已另有用途，自动配对不会用它；确认是平台回款再手动配"><Tag color="orange" bordered={false}>{line.journal_hint}</Tag></Tooltip>
            : <Tag color="green" bordered={false}>可配</Tag>) },
        ]}
        locale={{ emptyText: lines.error ? reconErrorText(lines.error) : "这家店的收款账户里没有可配的到账（先在「收款账户匹配」里设好账户）" }}
      />
      {lines.data?.truncated && <Typography.Paragraph type="warning">只列出最近 {lines.data.limit} 笔，更早的没有显示。</Typography.Paragraph>}
      {others.length > 0 && (
        <>
          <Divider orientation="left" plain>合并打款：一起配的其他期</Divider>
          <Checkbox.Group value={extra} onChange={(value) => setExtra(value.map(String))}
            options={others.map((item) => ({ value: item.key, label: `${item.payDate} · 应付 $${n2(item.payable)}` }))} />
        </>
      )}
      <Typography.Paragraph className="fin-payout-recon__hint">
        这次配 {chosen.length} 期，应付合计 ${n2(payable)}{picked ? ` · 到账 $${n2(Number(picked.amount))} · 差额 $${n2(Number(picked.amount) - payable)}` : ""}
      </Typography.Paragraph>
      <Input.TextArea rows={2} maxLength={300} value={note} onChange={(event) => setNote(event.target.value)} placeholder="备注（选填）" />
    </Modal>
  );
}

function PeriodDrawer({ row, openRows, onPass, onReject, onChanged, onClose }: PeriodDrawerProps) {
  const [messageApi, holder] = message.useMessage();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [matching, setMatching] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const [undoReason, setUndoReason] = useState("");
  const detail = usePeriodDetail(row);
  if (!row) return null;
  const matched = isMatched(row);
  const stage = row.stage;
  const finalTurn = matched && !row.arrivalVoided && stage === "ok1";
  const turnTip = row.arrivalVoided ? VOIDED_ARRIVAL_TEXT : !matched ? "还没配上到账，不审核" : finalTurn ? "" : stage === "ok2" ? "已终审" : "还没初审通过，轮不到终审";
  const canChangeMatch = isFirstPending(stage) || row.arrivalVoided;
  const undo = async () => {
    try {
      await undoMatch(row.matchId, undoReason.trim());
      void messageApi.success("已撤销配对，日记账备注 / 分类已恢复");
      setUndoing(false);
      setUndoReason("");
      onChanged();
    } catch (error) {
      void messageApi.error(reconErrorText(error));
    }
  };
  const data = detail.data;
  const records = data ? [
    ...data.reviews.map((item) => ({ at: item.created_at, text: KIND_TEXT[item.kind] ?? item.kind, detail: item.reason })),
    ...data.matches.flatMap((item) => [
      { at: item.created_at, text: item.method === "auto" ? "自动配对" : "手动配对", detail: null as string | null },
      ...(item.undone_at ? [{ at: item.undone_at, text: "撤销配对", detail: item.undo_reason }] : []),
    ]),
  ].sort((a, b) => b.at.localeCompare(a.at)) : [];
  return (
    <Drawer
      open
      rootClassName="fin-payout-recon__drawer"
      width={760}
      onClose={onClose}
      title={`${row.code} · 账单日 ${row.payDate}`}
      footer={
        <div className="fin-payout-recon__footer">
          <Tooltip title={turnTip}><Button type="primary" icon={<CheckOutlined aria-hidden="true" />} disabled={!finalTurn} onClick={() => onPass(row)}>终审通过</Button></Tooltip>
          <Tooltip title={turnTip || "必填原因，驳回到待初审"}><Button danger icon={<CloseOutlined aria-hidden="true" />} disabled={!finalTurn} onClick={() => setRejecting(true)}>终审不通过</Button></Tooltip>
        </div>
      }
    >
      {holder}
      <Descriptions size="small" column={2} bordered>
        <Descriptions.Item label="店铺">{row.code}</Descriptions.Item>
        <Descriptions.Item label="收款机构">{row.org || "未匹配"}</Descriptions.Item>
        <Descriptions.Item label="收款账户">{row.payee || "未匹配"}</Descriptions.Item>
        <Descriptions.Item label="账期">{row.cycleFrom ? `${row.cycleFrom} ~ ${row.cycleTo}` : "—"}</Descriptions.Item>
        <Descriptions.Item label="账单日">{row.payDate}</Descriptions.Item>
        <Descriptions.Item label="应付"><MoneyCell value={row.payable} /></Descriptions.Item>
        <Descriptions.Item label="到账">{row.arrived == null ? "—" : <MoneyCell value={row.arrived} />}</Descriptions.Item>
        <Descriptions.Item label="回款状态">
          <Space size={4}>
            <Tag color={PAY_STATE[row.state].color} bordered={false}>{PAY_STATE[row.state].text}</Tag>
            {row.state === "mismatch" && <Typography.Text type="danger">差额 ${n2(row.diff)}</Typography.Text>}
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="审核" span={2}>{matched ? `${REVIEW_TAG[stage].text}${row.stageReason ? `（原因：${row.stageReason}）` : ""}` : "还没配上到账，不审核"}</Descriptions.Item>
      </Descriptions>

      <Divider orientation="left" plain>配对的到账（日记账）</Divider>
      {matched ? (
        <>
          {row.arrivalVoided && <Alert className="fin-payout-recon__gap" type="error" showIcon message={VOIDED_ARRIVAL_TEXT} description="这笔到账所在的日记账批次已作废，这一期按没到账算。撤销配对后重新配。" />}
          <Descriptions size="small" column={2} bordered>
            <Descriptions.Item label="到账日期">{row.arrivedAt || "—"}</Descriptions.Item>
            <Descriptions.Item label="入账账户（日记账）">{row.accountName || "—"}</Descriptions.Item>
            <Descriptions.Item label="配对方式">{row.matchMethod === "auto" ? "自动" : "手动"}{row.matchSize > 1 ? ` · 合并打款 ${row.matchSize} 期` : ""}</Descriptions.Item>
            <Descriptions.Item label="流水编号">{row.lineUid}</Descriptions.Item>
          </Descriptions>
          <Tooltip title={canChangeMatch ? "撤销后日记账的备注 / 自动填的分类恢复原样" : "已初审 / 终审的不能撤销配对，先请终审驳回"}>
            <Button className="fin-payout-recon__gap" disabled={!canChangeMatch} onClick={() => setUndoing(true)}>撤销配对</Button>
          </Tooltip>
        </>
      ) : (
        <Space direction="vertical">
          <Typography.Text type="secondary">{row.state === "no_pay" ? "本期不需打款。" : row.state === "voided" ? "账单作废，不配到账。" : "还没配上到账。自动配对没配上的（金额不等、几笔对不清）在这里手动配。"}</Typography.Text>
          {row.state !== "no_pay" && row.state !== "voided" && <Button type="primary" onClick={() => setMatching(true)}>手动配对</Button>}
        </Space>
      )}

      <Divider orientation="left" plain>按金额类型小计（沃尔玛账单）</Divider>
      {data && Object.keys(data.amounts_by_type).length ? (
        <Descriptions size="small" column={2} bordered>
          {Object.entries(data.amounts_by_type).map(([kind, amount]) => <Descriptions.Item key={kind} label={kind}><MoneyCell value={Number(amount)} /></Descriptions.Item>)}
        </Descriptions>
      ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={detail.isPending ? "加载中" : "没有小计"} />}

      <Divider orientation="left" plain>跟进记录</Divider>
      {data?.follow_ups.length ? (
        <Timeline
          items={[...data.follow_ups].reverse().map((item) => ({
            children: (
              <>
                <Typography.Text className="finance-board__fulltext">{item.content}</Typography.Text>
                <br />
                <Typography.Text type="secondary">{timeText(item.created_at)}{item.case_no ? ` · Case ${item.case_no}` : ""}{item.next_follow_date ? ` · 下次跟进 ${item.next_follow_date}` : ""}</Typography.Text>
              </>
            ),
          }))}
        />
      ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有跟进记录" />}

      <Divider orientation="left" plain>审核与配对记录</Divider>
      {records.length ? (
        <Timeline items={records.map((item) => ({ children: <><Typography.Text>{item.text}</Typography.Text>{item.detail && <Typography.Text type="secondary">（{item.detail}）</Typography.Text>}<br /><Typography.Text type="secondary">{timeText(item.at)}</Typography.Text></> }))} />
      ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有操作" />}

      <Modal
        open={rejecting}
        title={`终审不通过 · ${row.code} · ${row.payDate}`}
        okText="确定驳回"
        okButtonProps={{ danger: true, disabled: !reason.trim() }}
        cancelText="取消"
        onOk={() => { onReject(row, reason.trim()); setRejecting(false); setReason(""); }}
        onCancel={() => { setRejecting(false); setReason(""); }}
        destroyOnHidden
      >
        <Input.TextArea autoFocus rows={3} maxLength={300} showCount value={reason} onChange={(event) => setReason(event.target.value)} placeholder="必填：驳回原因（显示在审核状态下，财务专员据此处理）" />
      </Modal>
      <Modal open={undoing} title={`撤销配对 · ${row.code} · ${row.payDate}`} okText="确定撤销" okButtonProps={{ danger: true, disabled: !undoReason.trim() }} cancelText="取消"
        onOk={() => void undo()} onCancel={() => { setUndoing(false); setUndoReason(""); }} destroyOnHidden>
        {row.matchSize > 1 && <Typography.Paragraph type="warning">这是合并打款，{row.matchSize} 期会一起撤销。</Typography.Paragraph>}
        <Input.TextArea autoFocus rows={3} maxLength={300} showCount value={undoReason} onChange={(event) => setUndoReason(event.target.value)} placeholder="必填：撤销原因" />
      </Modal>
      {matching && <MatchModal row={row} openRows={openRows} onClose={() => setMatching(false)} onDone={() => { setMatching(false); onChanged(); }} />}
    </Drawer>
  );
}

export default PeriodDrawer;

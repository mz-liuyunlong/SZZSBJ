/** 流水详情抽屉和其中的异常说明；从 FinanceCashFlowPage.tsx 原样搬出。 */
import { CheckOutlined, CloseOutlined } from "@ant-design/icons";
import { Button, Descriptions, Divider, Drawer, Space, Tag, Tooltip, Typography } from "antd";
import { FinMoney, LOCKED_TIP } from "@/pages/finance/FinanceBoardFrame";
import { asLive, type LiveCashLine } from "@/pages/finance/cash-flow/journalApi";
import { ALERT_GUIDE, alertShort, type CashAlert, type FsDetail } from "@/pages/finance/cash-flow/data";
import { accountLabel, type CashLine, type CashSnapshot, type FeishuApproval } from "@/pages/finance/localFinData";
import { EMPTY, type ReviewMark, REVIEW_TAG, baseReview, PREVIEW_ACTION_TIP, type ApprovalView, amountDiff, compareRows } from "@/pages/finance/cash-flow/journalShared";
import { CompareTable, ApprovalPanel } from "@/pages/finance/cash-flow/ApprovalDrawer";
import { EditableText, ReviewUndo, SplitButton, SplitParts } from "@/pages/finance/cash-flow/LineActions";

/* ======================================================= 异常（并入日记账；不分等级，所有异常都要处理） */
export function AlertSection({ alerts }: { alerts: CashAlert[] }) {
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
export function LineDrawer({ line, review, data, details, approvalsOf, alerts, live, onClose, onOpenApproval, onPass, onReject, onExclude, onUnexclude }: {
  line?: CashLine; review?: ReviewMark; data: CashSnapshot; alerts: CashAlert[]; details: Record<string, FsDetail>; approvalsOf: (line: CashLine) => ApprovalView[];
  live?: boolean; onClose: () => void; onOpenApproval: (item: FeishuApproval) => void; onPass: (line: CashLine) => void; onReject: (line: CashLine) => void; onExclude?: (line: LiveCashLine) => void; onUnexclude?: (line: LiveCashLine) => void;
}) {
  if (!line) return null;
  const account = data.accounts.find((item) => item.id === line.acct);
  const cat = data.cats.find((item) => item.code === line.cat);
  const approvals = new Map(data.feishu.map((item) => [item.serial, item]));
  const mark = review ?? baseReview(line);
  const views = approvalsOf(line);
  const finalTurn = mark.stage === "ok1";
  const turnTip = finalTurn ? "" : mark.stage === "ok2" ? "已终审" : "还没初审通过，轮不到终审";
  const liveLine = live ? asLive(line) : undefined;
  return (
    <Drawer open width={720} rootClassName="fin-cash-flow__drawer" onClose={onClose} title={`流水 ${line.date} · ${accountLabel(account) || line.acct}`}
      extra={<Space>{liveLine ? <SplitButton key={liveLine.id} line={liveLine} /> : <Tooltip title={LOCKED_TIP}><Button disabled>拆分</Button></Tooltip>}{liveLine ? (liveLine.excludeReason ? <Button danger onClick={() => onUnexclude?.(liveLine)}>撤销剔除</Button> : <Button danger onClick={() => onExclude?.(liveLine)}>剔除</Button>) : <Tooltip title={LOCKED_TIP}><Button danger disabled>剔除</Button></Tooltip>}</Space>}
      footer={<div className="fin-cash-flow__footer">
        {liveLine && <ReviewUndo key={liveLine.id} line={liveLine} stage={mark.stage} />}
        <Tooltip title={turnTip || (live ? "" : PREVIEW_ACTION_TIP)}><Button type="primary" icon={<CheckOutlined aria-hidden="true" />} disabled={!finalTurn} onClick={() => onPass(line)}>终审通过</Button></Tooltip>
        <Tooltip title={turnTip || "必填原因，驳回到待初审"}><Button danger icon={<CloseOutlined aria-hidden="true" />} disabled={!finalTurn} onClick={() => onReject(line)}>终审不通过</Button></Tooltip>
      </div>}>
      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="流水 id">{line.id}</Descriptions.Item>
        <Descriptions.Item label="日期 / 时间">{line.date} {line.time ?? ""}</Descriptions.Item>
        <Descriptions.Item label="金额"><FinMoney value={line.amt} cur={line.cur} masked={line.masked} /></Descriptions.Item>
        {line.cur !== "CNY" && <Descriptions.Item label="折人民币"><FinMoney value={line.cny} masked={line.masked} /></Descriptions.Item>}
        <Descriptions.Item label="余额"><FinMoney value={line.bal ?? null} cur={line.cur} masked={line.masked} /></Descriptions.Item>
        <Descriptions.Item label="摘要">{line.masked ? "****" : liveLine ? <EditableText key={`${liveLine.id}-sum`} line={liveLine} field="description" /> : line.sum || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="备注">{line.masked ? "****" : liveLine ? <EditableText key={`${liveLine.id}-memo`} line={liveLine} field="memo" /> : line.memo || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="对方">{line.party || EMPTY}</Descriptions.Item>
        {liveLine?.parts?.length ? <Descriptions.Item label={`拆分（${liveLine.parts.length} 行）`}><SplitParts line={liveLine} data={data} /></Descriptions.Item> : <Descriptions.Item label="类别">{line.cat ? `${line.cat} ${cat?.big ?? ""}·${cat?.name ?? ""}` : <Tag color="red" bordered={false}>待分类</Tag>}<Typography.Text type="secondary">（来源：{line.cat_src || "—"}）</Typography.Text></Descriptions.Item>}
        <Descriptions.Item label="配对">{line.pair || EMPTY}</Descriptions.Item>
        <Descriptions.Item label="标记">{line.flags.length ? line.flags.map((flag) => <Tag key={flag} bordered={false}>{flag}</Tag>) : EMPTY}</Descriptions.Item>
        {liveLine?.excludeReason && <Descriptions.Item label="剔除原因">{liveLine.excludeReason}</Descriptions.Item>}
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
      <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>类别、关联审批单在表格行上直接改；初审在表格右侧 ✓ ✗，终审可以在这里点；初审、终审点错了可以在底部撤销。审核后再改类别 / 关联审批单 / 拆分 / 剔除会自动退回待初审；改摘要、备注不会。{live ? "审批单内容和凭证要等飞书同步上线后才有。" : Object.keys(details).length ? "" : "（审批单凭证数据没读到：先在 Mac 上运行 local_export/cash-flow.py）"}</Typography.Paragraph>
    </Drawer>
  );
}

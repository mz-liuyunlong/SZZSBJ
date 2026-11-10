/**
 * 回款对账：批量审核（照日记账）+ 导出 Excel。
 * - 批量确认到账（初审）/ 批量终审通过 / 批量终审驳回（填一次原因写到每一期）；不在这一步的期次跳过（后端也会再判一次）。
 * - 导出：有勾选导出勾选的，没勾选导出当前表格里的全部期次。
 */
import { DownOutlined } from "@ant-design/icons";
import { Button, Dropdown, Input, Modal, Tooltip, Typography, message } from "antd";
import { useState } from "react";
import * as XLSX from "xlsx";
import { postReview, reconErrorText, type ReconRow, type ReviewKind } from "./reconApi";
import { PAY_STATE, REVIEW_TAG, isFirstPending, isMatched } from "./reconModel";

const BATCH: Record<ReviewKind, { label: string; danger?: boolean; skipText: string }> = {
  review1_pass: { label: "批量确认到账（初审）", skipText: "还没配上到账或不在待初审" },
  review2_pass: { label: "批量终审通过", skipText: "不在待终审" },
  review2_reject: { label: "批量终审驳回", danger: true, skipText: "不在待终审" },
};

const eligible = (row: ReconRow, kind: ReviewKind) => isMatched(row) && (kind === "review1_pass" ? isFirstPending(row.stage) : row.stage === "ok1");

function ReconBatch({ rows, selected, onDone }: { rows: ReconRow[]; selected: ReconRow[]; onDone: () => void }) {
  const [messageApi, holder] = message.useMessage();
  const [pending, setPending] = useState<ReviewKind>();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const todo = pending ? selected.filter((row) => eligible(row, pending)) : [];
  const close = () => { setPending(undefined); setReason(""); };
  const run = async () => {
    if (!pending || !todo.length) return;
    setBusy(true);
    try {
      const result = await postReview(pending, todo, pending === "review2_reject" ? reason.trim() : undefined);
      const skipped = selected.length - result.done;
      void messageApi.success(`${BATCH[pending].label.replace("批量", "")} ${result.done} 期${skipped > 0 ? `，跳过 ${skipped} 期` : ""}`);
      close();
      onDone();
    } catch (error) {
      void messageApi.error(reconErrorText(error));
    } finally {
      setBusy(false);
    }
  };

  const exportExcel = () => {
    const source = selected.length ? selected : rows;
    if (!source.length) { void messageApi.info("当前没有期次可导出"); return; }
    const header = ["店铺", "账单日", "收款机构", "收款账户", "入账账户", "账期", "应付", "到账", "差额", "到账日期", "配对方式", "回款状态", "Case 编号", "下次跟进", "最新跟进", "审核状态", "驳回原因"];
    const body = source.map((row) => [
      row.code, row.payDate, row.org, row.payee, row.accountName, row.cycleFrom ? `${row.cycleFrom} ~ ${row.cycleTo}` : "", row.payable, row.arrived ?? "", row.diff ?? "", row.arrivedAt,
      row.matchMethod === "auto" ? "自动" : row.matchMethod === "manual" ? "手动" : "", PAY_STATE[row.state].text,
      row.latestFollow?.case_no ?? "", row.latestFollow?.next_follow_date ?? "", row.latestFollow?.content ?? "",
      isMatched(row) ? REVIEW_TAG[row.stage].text : "不需审核", row.stageReason,
    ]);
    const sheet = XLSX.utils.aoa_to_sheet([header, ...body]);
    sheet["!cols"] = header.map((title) => ({ wch: ["收款账户", "最新跟进"].includes(title) ? 30 : title === "账期" ? 24 : 12 }));
    const book = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(book, sheet, "回款对账");
    const now = new Date();
    const pad = (value: number) => String(value).padStart(2, "0");
    XLSX.writeFile(book, `回款对账_${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}_${source.length}期.xlsx`);
    void messageApi.success(`已导出 ${source.length} 期${selected.length ? "（勾选的）" : "（当前表格）"}`);
  };

  const items = (Object.keys(BATCH) as ReviewKind[]).map((kind) => ({ key: kind, danger: BATCH[kind].danger, label: BATCH[kind].label }));
  return (
    <>
      {holder}
      <Tooltip title={selected.length ? "" : "先在表格最左边勾选期次"}>
        <Dropdown disabled={!selected.length} trigger={["click"]} menu={{ items, onClick: ({ key }) => setPending(key as ReviewKind) }}>
          <Button>批量操作{selected.length ? `（${selected.length}）` : ""} <DownOutlined aria-hidden="true" /></Button>
        </Dropdown>
      </Tooltip>
      <Tooltip title={selected.length ? `导出勾选的 ${selected.length} 期` : `导出当前表格里的 ${rows.length} 期`}>
        <Button onClick={exportExcel}>导出 Excel</Button>
      </Tooltip>
      <Modal open={Boolean(pending)} title={pending ? BATCH[pending].label : ""} okText={`确定（${todo.length} 期）`} cancelText="取消" confirmLoading={busy}
        okButtonProps={{ danger: pending ? BATCH[pending].danger : false, disabled: !todo.length || (pending === "review2_reject" && !reason.trim()) }} onOk={() => void run()} onCancel={close} destroyOnHidden>
        {pending && <>
          <Typography.Paragraph>勾选 {selected.length} 期，这次处理 <Typography.Text strong>{todo.length}</Typography.Text> 期。</Typography.Paragraph>
          {selected.length > todo.length && <Typography.Paragraph type="secondary">跳过 {selected.length - todo.length} 期：{BATCH[pending].skipText}。</Typography.Paragraph>}
          {pending === "review2_reject" && <>
            <Typography.Paragraph type="secondary">驳回后回到待初审。</Typography.Paragraph>
            <Input.TextArea autoFocus rows={3} maxLength={300} showCount value={reason} onChange={(event) => setReason(event.target.value)} placeholder="必填：驳回原因（写到每一期）" />
          </>}
        </>}
      </Modal>
    </>
  );
}

export default ReconBatch;

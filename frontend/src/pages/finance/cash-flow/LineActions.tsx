/**
 * 流水详情里的人工动作（rocky 11-05）：改摘要 / 备注、撤销初审 / 终审、拆分后逐行选类别。
 * 每个动作都是一条流水事件（带版本号），写完重读日记账；详情抽屉跟着显示最新的那一行。
 */
import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Input, InputNumber, Modal, Popconfirm, Select, Space, Table, Tag, Tooltip, Typography, message } from "antd";
import { useMemo, useState, type ReactNode } from "react";
import { FinMoney } from "@/pages/finance/FinanceBoardFrame";
import { asLive, cashErrorText, postLineEvent, useRefreshJournal, type LineEventKind, type LiveCashLine } from "@/pages/finance/cash-flow/journalApi";
import { EMPTY, type ReviewStage } from "@/pages/finance/cash-flow/journalShared";
import type { CashLine, CashSnapshot } from "@/pages/finance/localFinData";

/** 写一条事件：成功提示、失败给原因，不管成败都重读（失败多半是别人刚改过）。 */
function useLineEvent() {
  const refresh = useRefreshJournal();
  const [messageApi, holder] = message.useMessage();
  const [busy, setBusy] = useState(false);
  const send = async (line: LiveCashLine, kind: LineEventKind, payload: Record<string, unknown>, done: string) => {
    setBusy(true);
    let ok = false;
    try {
      const result = await postLineEvent(line, kind, { payload });
      ok = true;
      void messageApi.success(done);
      if (result.auto_reset) void messageApi.info("这笔已审过，改动后自动退回待初审");
    } catch (error) {
      void messageApi.error(cashErrorText(error));
    }
    setBusy(false);
    void refresh();
    return ok;
  };
  return { send, busy, holder };
}

/** 表格里的摘要 / 备注格子：接口数据可以直接在行上改（rocky 11-05）；Demo 数据原样显示。children 是原来的显示内容。 */
export function CellText({ line, field, children }: { line: CashLine; field: "description" | "memo"; children: ReactNode }) {
  const live = asLive(line);
  if (!live) return <>{children}</>;
  return <EditableText key={live.id} line={live} field={field} compact>{children}</EditableText>;
}

/** 摘要 / 备注：显示改过的内容，旁边标「已改」（鼠标放上去看银行原文）；点铅笔改，清空保存 = 恢复原文。不退回审核。
 * compact = 表格格子：显示 children（表格原来的样式），编辑框收窄，不显示原文说明。 */
export function EditableText({ line, field, compact, children }: { line: LiveCashLine; field: "description" | "memo"; compact?: boolean; children?: ReactNode }) {
  const { send, busy, holder } = useLineEvent();
  const value = field === "description" ? line.sum : line.memo;
  const original = field === "description" ? line.origSum : line.origMemo;
  const [draft, setDraft] = useState<string>();
  const save = async () => {
    if (draft === undefined) return;
    if (await send(line, "set_text", { [field]: draft.trim() || null }, draft.trim() ? "已保存" : "已恢复银行原文")) setDraft(undefined);
  };
  if (draft !== undefined) {
    return (
      <Space direction="vertical" size={4} style={{ width: "100%" }}>
        {holder}
        <Input.TextArea autoFocus autoSize={{ minRows: 1, maxRows: 4 }} maxLength={500} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") setDraft(undefined); }} onPressEnter={(event) => { if (!event.shiftKey) { event.preventDefault(); void save(); } }} />
        <Space size={8} wrap>
          <Button size="small" type="primary" loading={busy} onClick={() => void save()}>保存</Button>
          <Button size="small" onClick={() => setDraft(undefined)}>取消</Button>
          {compact ? <Tooltip title={`银行原文：${original || "（空）"}；清空保存就恢复原文`}><Typography.Text type="secondary">原文</Typography.Text></Tooltip> : <Typography.Text type="secondary">银行原文：{original || EMPTY}；清空保存就恢复原文</Typography.Text>}
        </Space>
      </Space>
    );
  }
  const edited = value !== original && <Tooltip title={`银行原文：${original || "（空）"}`}><Tag bordered={false} color="gold">已改</Tag></Tooltip>;
  const pencil = <Tooltip title={field === "description" ? "改摘要（只改显示，不退回审核）" : "改备注（只改显示，不退回审核）"}><Button size="small" type="text" className="fin-cash-flow__cell-edit" aria-label={field === "description" ? "改摘要" : "改备注"} icon={<EditOutlined aria-hidden="true" />} onClick={() => setDraft(value)} /></Tooltip>;
  if (compact) {
    return <div className="fin-cash-flow__cell-text">{holder}<div className="fin-cash-flow__cell-body">{children}</div>{edited}{pencil}</div>;
  }
  return (
    <Space size={6} wrap>
      {holder}
      <span>{value || EMPTY}</span>
      {edited}
      {pencil}
    </Space>
  );
}

/** 撤销审核：初审后（通过 / 不通过）可撤销初审，能做初审的人都可以撤；终审后（通过 / 驳回）可撤销终审，回到待终审。 */
export function ReviewUndo({ line, stage }: { line: LiveCashLine; stage: ReviewStage }) {
  const { send, busy, holder } = useLineEvent();
  const first = stage === "ok1" || stage === "rej1";
  const final = stage === "ok2" || stage === "rej2";
  if (!first && !final) return null;
  const title = first ? "撤销初审，回到待初审？" : "撤销终审，回到待终审？";
  return (
    <>
      {holder}
      <Popconfirm title={title} okText="撤销" cancelText="取消" onConfirm={() => void send(line, first ? "review1_undo" : "review2_undo", {}, first ? "已撤销初审" : "已撤销终审")}>
        <Button loading={busy}>{first ? "撤销初审" : "撤销终审"}</Button>
      </Popconfirm>
    </>
  );
}

const round2 = (value: number) => Math.round(value * 100) / 100;

/** 拆分：先把金额拆成几行（合计 = 这笔流水金额），拆完再在详情里逐行选类别。已拆分的可以取消拆分。 */
export function SplitButton({ line }: { line: LiveCashLine }) {
  const { send, busy, holder } = useLineEvent();
  const [amounts, setAmounts] = useState<(number | null)[]>();
  const total = round2(Math.abs(line.amt ?? 0));
  const filled = round2((amounts ?? []).reduce<number>((sum, value) => sum + (value ?? 0), 0));
  const rest = round2(total - filled);
  const valid = Boolean(amounts && amounts.length >= 2 && amounts.every((value) => value != null && value > 0) && rest === 0);
  const open = () => setAmounts([null, null]);
  const submit = async () => {
    if (!amounts || !valid) return;
    if (await send(line, "split", { amounts: amounts.map((value) => String(value)) }, `已拆成 ${amounts.length} 行，请逐行选类别`)) setAmounts(undefined);
  };
  if (line.parts?.length) {
    return (
      <>
        {holder}
        <Popconfirm title="取消拆分？各行选好的类别会清掉，回到整笔一个类别。" okText="取消拆分" cancelText="不了" onConfirm={() => void send(line, "unsplit", {}, "已取消拆分")}>
          <Button loading={busy}>取消拆分</Button>
        </Popconfirm>
      </>
    );
  }
  return (
    <>
      {holder}
      <Tooltip title={line.excludeReason ? "已剔除的要先撤销剔除" : "把一笔拆成几行，各行再选类别"}><Button disabled={Boolean(line.excludeReason)} onClick={open}>拆分</Button></Tooltip>
      <Modal open={Boolean(amounts)} title="拆分这笔流水" okText="拆分" cancelText="取消" confirmLoading={busy} okButtonProps={{ disabled: !valid }} onOk={() => void submit()} onCancel={() => setAmounts(undefined)} destroyOnHidden>
        <Typography.Paragraph>这笔金额 <FinMoney value={total} cur={line.cur} />。每行填金额（正数），合计要正好等于这笔金额；拆完在详情里逐行选类别。已审过的拆分后会退回待初审。</Typography.Paragraph>
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          {(amounts ?? []).map((value, index) => (
            <Space key={index} size={8}>
              <Typography.Text type="secondary">第 {index + 1} 行</Typography.Text>
              <InputNumber aria-label={`第 ${index + 1} 行金额`} style={{ width: 200 }} min={0.01} precision={2} value={value}
                onChange={(next) => setAmounts((current) => current?.map((item, at) => (at === index ? (next == null ? null : Number(next)) : item)))} />
              {index === (amounts ?? []).length - 1 && rest > 0 && <Button size="small" type="link" onClick={() => setAmounts((current) => current?.map((item, at) => (at === index ? round2((item ?? 0) + rest) : item)))}>填入剩余 {rest.toFixed(2)}</Button>}
              {(amounts ?? []).length > 2 && <Button size="small" type="text" danger aria-label="删掉这行" icon={<DeleteOutlined aria-hidden="true" />} onClick={() => setAmounts((current) => current?.filter((_, at) => at !== index))} />}
            </Space>
          ))}
          <Button size="small" icon={<PlusOutlined aria-hidden="true" />} disabled={(amounts ?? []).length >= 20} onClick={() => setAmounts((current) => [...(current ?? []), null])}>加一行</Button>
          <Typography.Text type={rest === 0 ? "success" : "danger"}>已填 {filled.toFixed(2)} / {total.toFixed(2)}{rest !== 0 ? `，还差 ${rest.toFixed(2)}` : "，正好"}</Typography.Text>
        </Space>
      </Modal>
    </>
  );
}

/** 拆分后的各行：金额 + 类别下拉（按大类分组，可搜索；X01 不能选，剔除用剔除按钮）。 */
export function SplitParts({ line, data }: { line: LiveCashLine; data: CashSnapshot }) {
  const { send, busy, holder } = useLineEvent();
  const options = useMemo(() => {
    const groups = new Map<string, { value: string; label: string }[]>();
    for (const cat of data.cats) {
      if (cat.code === "X01") continue;
      groups.set(cat.big, [...(groups.get(cat.big) ?? []), { value: cat.code, label: `${cat.code} ${cat.big}·${cat.name}` }]);
    }
    return Array.from(groups, ([big, items]) => ({ label: big, title: big, options: items }));
  }, [data.cats]);
  const rows = (line.parts ?? []).map((part, index) => ({ ...part, index }));
  return (
    <>
      {holder}
      <Table size="small" pagination={false} rowKey="index" dataSource={rows} columns={[
        { key: "no", title: "行", width: 48, render: (_, row) => row.index + 1 },
        { key: "amt", title: "金额", width: 140, align: "right", render: (_, row) => <FinMoney value={row.amt} cur={line.cur} /> },
        { key: "cat", title: "类别", render: (_, row) => (
          <Select size="small" showSearch style={{ width: 260 }} disabled={busy} value={row.cat || undefined} options={options} placeholder={<Typography.Text type="danger">待分类</Typography.Text>}
            filterOption={(input, option) => String(option?.label ?? "").toLowerCase().includes(input.trim().toLowerCase())}
            onChange={(value: string) => void send(line, "set_part_category", { index: row.index, category_code: value }, `第 ${row.index + 1} 行已选类别`)} />
        ) },
      ]} />
    </>
  );
}

/**
 * 流水详情里的人工动作（rocky 11-05）：改摘要 / 备注、撤销初审 / 终审、拆分后逐行选类别。
 * 每个动作都是一条流水事件（带版本号），写完重读日记账；详情抽屉跟着显示最新的那一行。
 */
import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Input, InputNumber, Modal, Popconfirm, Radio, Select, Space, Table, Tag, Tooltip, Typography, message } from "antd";
import { useMemo, useState, type ReactNode } from "react";
import { FinMoney } from "@/pages/finance/FinanceBoardFrame";
import { asLive, cashErrorText, postLineEvent, useRefreshJournal, type LineEventKind, type LiveCashLine } from "@/pages/finance/cash-flow/journalApi";
import type { CashAlert } from "@/pages/finance/cash-flow/data";
import { EMPTY, FEE_ALERT_TYPES, type ReviewStage } from "@/pages/finance/cash-flow/journalShared";
import { catFilter, groupedCatOptions } from "@/pages/finance/cash-flow/journalSelection";
import { PAIR_DAYS, pairCandidates, pairLines } from "@/pages/finance/cash-flow/journalPair";
import { cnyToOriginal, partCny } from "@/pages/finance/cash-flow/journalParts";
import { accountLabel, type CashLine, type CashSnapshot } from "@/pages/finance/localFinData";

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

/** 拆分：先把金额拆成几行（合计 = 这笔流水金额），拆完再在详情里逐行选类别。已拆分的可以取消拆分。
 * 外币流水有折人民币的，可以切到「按人民币填」，系统按这笔的实际汇率换回原币。 */
export function SplitButton({ line }: { line: LiveCashLine }) {
  const { send, busy, holder } = useLineEvent();
  const [amounts, setAmounts] = useState<(number | null)[]>();
  const total = round2(Math.abs(line.amt ?? 0));
  const totalCny = line.cur !== "CNY" && line.cny != null ? round2(Math.abs(line.cny)) : null;
  const [byCny, setByCny] = useState(false);
  const target = byCny && totalCny != null ? totalCny : total;
  const filled = round2((amounts ?? []).reduce<number>((sum, value) => sum + (value ?? 0), 0));
  const rest = round2(target - filled);
  const valid = Boolean(amounts && amounts.length >= 2 && amounts.every((value) => value != null && value > 0) && rest === 0);
  const originals = byCny && totalCny != null && valid ? cnyToOriginal((amounts ?? []).map((value) => value ?? 0), total, totalCny) : (amounts ?? []).map((value) => value ?? 0);
  const ready = valid && originals.every((value) => value > 0);
  const open = () => { setByCny(false); setAmounts([null, null]); };
  const switchMode = (next: boolean) => { setByCny(next); setAmounts((current) => current?.map(() => null)); };
  const submit = async () => {
    if (!amounts || !ready) return;
    if (await send(line, "split", { amounts: originals.map((value) => value.toFixed(2)) }, `已拆成 ${amounts.length} 行，请逐行选类别`)) setAmounts(undefined);
  };
  if (line.parts?.length) {
    return (
      <>
        {holder}
        <Popconfirm title="取消拆分？各行选好的类别会清掉（确认过的手续费行也一起取消），回到整笔一个类别。" okText="取消拆分" cancelText="不了" onConfirm={() => void send(line, "unsplit", {}, "已取消拆分")}>
          <Button loading={busy}>取消拆分</Button>
        </Popconfirm>
      </>
    );
  }
  const unit = byCny ? "¥" : "";
  return (
    <>
      {holder}
      <Tooltip title={line.excludeReason ? "已剔除的要先撤销剔除" : "把一笔拆成几行，各行再选类别"}><Button disabled={Boolean(line.excludeReason)} onClick={open}>拆分</Button></Tooltip>
      <Modal open={Boolean(amounts)} title="拆分这笔流水" okText="拆分" cancelText="取消" confirmLoading={busy} okButtonProps={{ disabled: !ready }} onOk={() => void submit()} onCancel={() => setAmounts(undefined)} destroyOnHidden>
        <Typography.Paragraph>这笔金额 <FinMoney value={total} cur={line.cur} />{totalCny != null ? <>（折人民币 <FinMoney value={totalCny} />）</> : null}。每行填金额（正数），合计要正好等于这笔金额；拆完在详情里逐行选类别。已审过的拆分后会退回待初审。</Typography.Paragraph>
        {totalCny != null && (
          <Radio.Group size="small" style={{ marginBottom: 12 }} value={byCny ? "cny" : "orig"} onChange={(event) => switchMode(event.target.value === "cny")}
            options={[{ value: "orig", label: `按${line.cur === "USD" ? "美元" : line.cur}填` }, { value: "cny", label: "按人民币填" }]} optionType="button" />
        )}
        {byCny && totalCny != null && <Typography.Paragraph type="secondary">按这笔的实际汇率 {(totalCny / total).toFixed(4)} 换回原币；尾差落在最后一行。</Typography.Paragraph>}
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          {(amounts ?? []).map((value, index) => (
            <Space key={index} size={8}>
              <Typography.Text type="secondary">第 {index + 1} 行</Typography.Text>
              <InputNumber aria-label={`第 ${index + 1} 行金额`} style={{ width: 200 }} min={0.01} precision={2} value={value} prefix={unit || undefined}
                onChange={(next) => setAmounts((current) => current?.map((item, at) => (at === index ? (next == null ? null : Number(next)) : item)))} />
              {byCny && ready && <Typography.Text type="secondary">= {originals[index].toFixed(2)} {line.cur}</Typography.Text>}
              {index === (amounts ?? []).length - 1 && rest > 0 && <Button size="small" type="link" onClick={() => setAmounts((current) => current?.map((item, at) => (at === index ? round2((item ?? 0) + rest) : item)))}>填入剩余 {rest.toFixed(2)}</Button>}
              {(amounts ?? []).length > 2 && <Button size="small" type="text" danger aria-label="删掉这行" icon={<DeleteOutlined aria-hidden="true" />} onClick={() => setAmounts((current) => current?.filter((_, at) => at !== index))} />}
            </Space>
          ))}
          <Button size="small" icon={<PlusOutlined aria-hidden="true" />} disabled={(amounts ?? []).length >= 20} onClick={() => setAmounts((current) => [...(current ?? []), null])}>加一行</Button>
          <Typography.Text type={rest === 0 ? "success" : "danger"}>已填 {unit}{filled.toFixed(2)} / {unit}{target.toFixed(2)}{rest !== 0 ? `，还差 ${rest.toFixed(2)}` : "，正好"}</Typography.Text>
        </Space>
      </Modal>
    </>
  );
}

/** 拆分后的各行：金额 + 类别下拉（按大类分组，可搜索；X01 不能选，剔除用剔除按钮）。 */
export function SplitParts({ line, data }: { line: LiveCashLine; data: CashSnapshot }) {
  const { send, busy, holder } = useLineEvent();
  const options = useMemo(() => groupedCatOptions(data.cats), [data.cats]);
  const rows = (line.parts ?? []).map((part, index) => ({ ...part, index }));
  const cnys = partCny(line);
  return (
    <>
      {holder}
      <Table size="small" pagination={false} rowKey="index" dataSource={rows} columns={[
        { key: "no", title: "行", width: 92, render: (_, row) => <Space size={4}>{row.index + 1}{row.fee && <Tag bordered={false} color="orange">手续费</Tag>}</Space> },
        { key: "amt", title: "金额", width: 140, align: "right", render: (_, row) => <FinMoney value={row.amt} cur={line.cur} /> },
        ...(line.cur !== "CNY" ? [{ key: "cny", title: "折人民币", width: 120, align: "right" as const, render: (_: unknown, row: { index: number }) => <FinMoney value={cnys[row.index]} /> }] : []),
        { key: "cat", title: "类别", render: (_, row) => (
          <Select size="small" showSearch style={{ width: 260 }} disabled={busy} value={row.cat || undefined} options={options} placeholder={<Typography.Text type="danger">待分类</Typography.Text>}
            filterOption={catFilter}
            onChange={(value: string) => void send(line, "set_part_category", { index: row.index, category_code: value }, `第 ${row.index + 1} 行已选类别`)} />
        ) },
      ]} />
    </>
  );
}

/** 「确认记为手续费」（rocky 11-05）：两边配上了但到账少一点，核对后点一下，把这笔拆成转账行 + 手续费行（F01）。
 * 不自动拆；哪些异常能点、切成哪一层手续费看 FEE_ALERT_TYPES。点错了用「取消拆分」。 */
export function FeeConfirm({ line, alert }: { line: LiveCashLine; alert: CashAlert }) {
  const { send, busy, holder } = useLineEvent();
  const layer = FEE_ALERT_TYPES[alert.type];
  const fee = Math.abs(alert.amt ?? 0);
  if (!layer || !fee) return null;
  const done = line.parts?.some((part) => part.fee === layer);
  if (done) return <Tag bordered={false} color="green">手续费已确认</Tag>;
  const total = Math.abs(line.amt ?? 0);
  const title = `扣款 ${total.toFixed(2)}，到账 ${(total - fee).toFixed(2)}，差额 ${fee.toFixed(2)} 记为手续费（F01）？这笔会拆成转账行和手续费行。`;
  return (
    <>
      {holder}
      <Popconfirm title={title} okText="确认" cancelText="取消" onConfirm={() => void send(line, "confirm_fee", { fee_amount: fee.toFixed(2), fee_layer: layer, alert_type: alert.type, transfer_category: line.cat && line.cat !== "X01" ? line.cat : null }, `已把 ${fee.toFixed(2)} 记为手续费`)}>
        <Button size="small" type="primary" ghost loading={busy}>确认记为手续费</Button>
      </Popconfirm>
    </>
  );
}

/** 详情里的「配对」/「取消配对」：配对从候选里选一笔；取消配对把同一组的几笔一起取消。 */
export function PairButton({ line, data, stageOf }: { line: LiveCashLine; data: CashSnapshot; stageOf: (line: CashLine) => ReviewStage }) {
  const refresh = useRefreshJournal();
  const [messageApi, holder] = message.useMessage();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  /* Rocky 11-10：有的要一笔配几笔（例如两笔付出、一笔退回），所以可以勾多笔；勾过的换了关键词也保留。 */
  const [chosenLines, setChosenLines] = useState<CashLine[]>([]);
  const [keyword, setKeyword] = useState("");
  const candidates = useMemo(() => {
    if (!open) return [];
    const names = new Map(data.accounts.map((item) => [item.id, accountLabel(item)]));
    return pairCandidates(line, data.lines, keyword, (acct) => names.get(acct) || acct);
  }, [open, line, data.lines, data.accounts, keyword]);
  const [unpairOpen, setUnpairOpen] = useState(false);
  const [unpairReason, setUnpairReason] = useState("");
  const run = async (lines: LiveCashLine[], kind: "pair" | "unpair", reason?: string) => {
    const locked = lines.filter((item) => stageOf(item) === "ok2");
    if (locked.length) { void messageApi.warning("有一笔已终审，先在它的详情里撤销终审再改配对"); return; }
    setBusy(true);
    const failed = await pairLines(lines, kind, reason);
    setBusy(false);
    setOpen(false);
    setUnpairOpen(false);
    setUnpairReason("");
    setPicked([]);
    setKeyword("");
    void refresh();
    if (failed.length) void messageApi.error(failed.join("；"));
    else void messageApi.success(kind === "pair" ? "已配对" : "已取消配对");
  };
  if (line.manualPair) {
    const group = data.lines.flatMap((item) => { const other = asLive(item); return other && other.manualPair === line.manualPair ? [other] : []; });
    return (
      <>
        {holder}
        <Button loading={busy} onClick={() => setUnpairOpen(true)}>取消配对</Button>
        <Modal open={unpairOpen} title={`取消这 ${group.length} 笔的人工配对`} okText="取消配对" cancelText="不了" confirmLoading={busy} okButtonProps={{ disabled: !unpairReason.trim() }}
          onOk={() => void run(group, "unpair", unpairReason.trim())} onCancel={() => { setUnpairOpen(false); setUnpairReason(""); }} destroyOnHidden>
          <Typography.Paragraph type="secondary">原因必填，会记在这几笔的操作记录里。</Typography.Paragraph>
          <Input.TextArea autoFocus aria-label="取消配对原因" placeholder="例如：配错了，应该配 10-24 那笔" maxLength={500} showCount autoSize={{ minRows: 2, maxRows: 4 }} value={unpairReason} onChange={(event) => setUnpairReason(event.target.value)} />
        </Modal>
      </>
    );
  }
  if (line.pair) return <Tooltip title="已自动配对"><Button disabled>配对</Button></Tooltip>;
  const chosen = chosenLines.filter((item) => picked.includes(item.id));
  const chosenSum = chosen.reduce((sum, item) => sum + (item.amt ?? 0), 0);
  const sameCur = chosen.every((item) => item.cur === line.cur);
  const groupGap = sameCur && chosen.length ? Math.round((Math.abs(line.amt ?? 0) - Math.abs(chosenSum)) * 100) / 100 : null;
  return (
    <>
      {holder}
      <Button onClick={() => setOpen(true)}>配对</Button>
      <Modal open={open} width={760} title="配对：选另一个账户里对应的那笔（可以勾几笔）" okText="配对" cancelText="取消" confirmLoading={busy} okButtonProps={{ disabled: !chosen.length }}
        onOk={() => { const others = chosen.flatMap((item) => { const other = asLive(item); return other ? [other] : []; }); if (others.length) void run([line, ...others], "pair"); }} onCancel={() => { setOpen(false); setKeyword(""); setPicked([]); }} destroyOnHidden>
        <Typography.Paragraph type="secondary">这笔 {line.date} <FinMoney value={line.amt} cur={line.cur} />。默认列出其他账户 {PAIR_DAYS} 天内方向相反、还没配对的流水，金额最接近的排前面；找不到就在下面搜索（不限日期）。两边金额有差的，配上后在异常里显示差额，可以确认记为手续费。</Typography.Paragraph>
        <Input.Search allowClear placeholder="搜索：账户、金额、摘要、备注、对方（空格隔开多个词）" style={{ marginBottom: 8 }} value={keyword} onChange={(event) => setKeyword(event.target.value)} />
        {chosen.length > 0 && <Typography.Paragraph>已选 {chosen.length} 笔，合计 <FinMoney value={chosenSum} cur={line.cur} />{groupGap != null ? <>，和这笔差 <Typography.Text type={Math.abs(groupGap) < 0.005 ? "success" : "warning"}>{groupGap.toFixed(2)}</Typography.Text></> : "（币种不同）"}</Typography.Paragraph>}
        <Table size="small" pagination={false} rowKey={(row) => row.line.id} dataSource={candidates} scroll={{ y: 360 }}
          rowSelection={{ type: "checkbox", selectedRowKeys: picked, preserveSelectedRowKeys: true, onChange: (keys, rows) => { setPicked(keys.map(String)); setChosenLines((current) => [...current.filter((item) => !rows.some((row) => row?.line.id === item.id)), ...rows.flatMap((row) => (row ? [row.line] : []))]); } }}
          onRow={(row) => ({ onClick: () => { setChosenLines((current) => (current.some((item) => item.id === row.line.id) ? current : [...current, row.line])); setPicked((current) => (current.includes(row.line.id) ? current.filter((id) => id !== row.line.id) : [...current, row.line.id])); } })}
          locale={{ emptyText: keyword.trim() ? "搜不到：换个关键词试试（金额可以只输整数部分）" : "15 天内没有候选：在上面搜索账户、金额或摘要" }}
          columns={[
            { key: "date", title: "日期", width: 100, render: (_, row) => row.line.date },
            { key: "acct", title: "账户", width: 160, render: (_, row) => accountLabel(data.accounts.find((item) => item.id === row.line.acct)) || row.line.acct },
            { key: "amt", title: "金额", width: 130, align: "right", render: (_, row) => <FinMoney value={row.line.amt} cur={row.line.cur} /> },
            { key: "diff", title: "差额", width: 90, align: "right", render: (_, row) => (Number.isFinite(row.diff) ? row.diff.toFixed(2) : "币种不同") },
            { key: "sum", title: "摘要 / 对方", ellipsis: true, render: (_, row) => [row.line.sum, row.line.party].filter(Boolean).join(" · ") || EMPTY },
          ]} />
      </Modal>
    </>
  );
}

/** 表格里拆分子行的类别格子：直接改这一行的类别（同一个可搜索的分组下拉）。 */
export function PartCategoryCell({ line, index, data, fee }: { line: LiveCashLine; index: number; data: CashSnapshot; fee?: string }) {
  const { send, busy, holder } = useLineEvent();
  const options = useMemo(() => groupedCatOptions(data.cats), [data.cats]);
  const part = line.parts?.[index];
  if (!part) return null;
  return (
    <span className="finance-board__stack">
      {holder}
      <Select size="small" showSearch filterOption={catFilter} popupMatchSelectWidth={280} style={{ width: 200 }} disabled={busy} value={part.cat || undefined} options={options}
        placeholder={<Typography.Text type="danger">待分类</Typography.Text>} onChange={(value: string) => void send(line, "set_part_category", { index, category_code: value }, `第 ${index + 1} 行已选类别`)} />
      <span className="finance-board__sub">{fee ? "手续费行" : "拆分行"}</span>
    </span>
  );
}

/** 表格里拆分子行的摘要 / 备注格子（rocky 11-05）：点铅笔改这一行自己的；清空保存 = 摘要沿用原行、备注清掉。不退回审核。 */
export function PartTextCell({ line, index, field, children }: { line: LiveCashLine; index: number; field: "description" | "memo"; children: ReactNode }) {
  const { send, busy, holder } = useLineEvent();
  const part = line.parts?.[index];
  const [draft, setDraft] = useState<string>();
  if (!part) return null;
  const own = (field === "description" ? part.sum : part.memo) ?? "";
  const label = field === "description" ? "摘要" : "备注";
  const save = async () => {
    if (draft === undefined) return;
    if (await send(line, "set_part_text", { index, [field]: draft.trim() || null }, draft.trim() ? `第 ${index + 1} 行${label}已保存` : `第 ${index + 1} 行${label}已清掉`)) setDraft(undefined);
  };
  if (draft !== undefined) {
    return (
      <Space direction="vertical" size={4} style={{ width: "100%" }}>
        {holder}
        <Input.TextArea autoFocus aria-label={`拆分第 ${index + 1} 行${label}`} autoSize={{ minRows: 1, maxRows: 4 }} maxLength={500} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") setDraft(undefined); }} onPressEnter={(event) => { if (!event.shiftKey) { event.preventDefault(); void save(); } }} />
        <Space size={8} wrap>
          <Button size="small" type="primary" loading={busy} onClick={() => void save()}>保存</Button>
          <Button size="small" onClick={() => setDraft(undefined)}>取消</Button>
          <Typography.Text type="secondary">{field === "description" ? "清空保存 = 沿用原行摘要" : "清空保存 = 不写备注"}</Typography.Text>
        </Space>
      </Space>
    );
  }
  return (
    <div className="fin-cash-flow__cell-text">
      {holder}
      <div className="fin-cash-flow__cell-body">{children}</div>
      <Tooltip title={`改拆分第 ${index + 1} 行的${label}（只改显示，不退回审核）`}><Button size="small" type="text" className="fin-cash-flow__cell-edit" aria-label={`改拆分第 ${index + 1} 行${label}`} icon={<EditOutlined aria-hidden="true" />} onClick={() => setDraft(own)} /></Tooltip>
    </div>
  );
}

/** 审批单：比对表、审批单面板、审批单详情抽屉；从 FinanceCashFlowPage.tsx 原样搬出。 */
import { Button, Descriptions, Divider, Drawer, Image, Space, Table, Tag, Typography } from "antd";
import { ProTable } from "@ant-design/pro-components";
import { FinMoney } from "@/pages/finance/FinanceBoardFrame";
import { fsFileUrl, type FsDetail, type FsRecord } from "@/pages/finance/cash-flow/data";
import { type CashSnapshot, type FeishuApproval } from "@/pages/finance/localFinData";
import { STATE_COLOR, EMPTY, type ApprovalView, viewOf, type CompareRow } from "@/pages/finance/cash-flow/journalShared";
import { CardText } from "@/pages/finance/cash-flow/CardText";

export function CompareTable({ rows }: { rows: CompareRow[] }) {
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
export function ApprovalPanel({ view, onOpen }: { view: ApprovalView; onOpen?: () => void }) {
  const hide = (value: string) => (view.masked ? "****" : value ? <CardText text={value} /> : EMPTY);
  const files = view.detail?.files ?? [];
  /* 接口版附件只存了元数据（name 为空），只列文件名，原件到飞书看。 */
  const images = files.filter((file) => file.img && file.name);
  const others = files.filter((file) => !file.img && file.name);
  const metaOnly = files.filter((file) => !file.name);
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
              { title: "意见 / 上传", dataIndex: "note", render: (_, row) => <>{row.note ? <CardText text={row.note} /> : ""}{row.files ? <Typography.Text type="secondary">{row.note ? "；" : ""}上传 {row.files} 个文件（见下方凭证）</Typography.Text> : row.note ? null : EMPTY}</> },
            ]} />
        </div>
      )}
      {(view.detail?.comments?.length ?? 0) > 0 && (
        <div className="fin-cash-flow__section">
          <Typography.Text strong>评论</Typography.Text>
          {view.detail?.comments?.map((row, index) => <div key={`${row.time}-${index}`}><Typography.Text type="secondary">{row.time} {row.who || "—"}：</Typography.Text>{row.note ? <CardText text={row.note} /> : "（只有附件）"}</div>)}
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
              {metaOnly.length > 0 && <div className="fin-cash-flow__section"><Typography.Text type="secondary">原件在飞书这张单上看：</Typography.Text>{metaOnly.map((file, index) => <div key={`${file.src}-${index}`}>{file.item ? `明细${file.item} · ` : ""}{file.what}{file.title && file.title !== "<nil>" ? `：${file.title}` : ""}</div>)}</div>}
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

/* ======================================================= 审批单详情抽屉 */
export function ApprovalDrawer({ item, data, details, onClose }: { item?: FeishuApproval; data: CashSnapshot; details: Record<string, FsDetail>; onClose: () => void }) {
  if (!item) return null;
  const lines = new Map(data.lines.map((line) => [line.id, line]));
  const accounts = new Map(data.accounts.map((account) => [account.id, account.name]));
  const hide = (value: string) => (item.masked ? "****" : value ? <CardText text={value} /> : EMPTY);
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
        return <div key={paid.line}><Tag bordered={false} color="blue">{paid.line}</Tag>{line ? `${line.date} ${accounts.get(line.acct) ?? line.acct} ` : ""}{paid.amt == null && item.state === "待定" ? "待定" : <FinMoney value={paid.amt ?? null} masked={item.masked} />}</div>;
      }) : <Typography.Text type="secondary">还没对上付款流水</Typography.Text>}
      <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>来源：{data.meta.feishu_src.join("；")}。正式系统由飞书审批 API 同步。</Typography.Paragraph>
    </Drawer>
  );
}

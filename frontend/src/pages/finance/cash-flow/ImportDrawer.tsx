/**
 * 日记账 ·「流水导入」抽屉（Rocky 2026-11-04：数据导入改为直接在日记账导入，不另开页面；原「数据导入」页保留、不上线）。
 * 内容取自「数据导入」的「现金流账户报表」一项（imports.json，本地预览只读）：交表节点、文件格式、各账户最近一次导入与覆盖范围。
 * 没有后端接口前，上传按钮和原导入页一样置灰（LOCKED_TIP）；交表人一律写角色。
 */
import { Alert, Button, Descriptions, Drawer, Space, Table, Tag, Tooltip, Typography } from "antd";
import { LOCKED_TIP } from "@/pages/finance/FinanceBoardFrame";
import { useImportsSnapshot, type ImportDetail } from "@/pages/finance/localFinData";
import EmptyState from "@/shared/states/EmptyState";

/** 「现金流账户报表」在 imports.json 里的 id。 */
const BANK_IMPORT_ID = "bank";

function ImportDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const snapshot = useImportsSnapshot();
  const item = snapshot.data?.items.find((row) => row.id === BANK_IMPORT_ID);
  const details = item?.detail ?? [];
  const missing = details.filter((row) => row.missing).length;
  return (
    <Drawer open={open} width={880} rootClassName="fin-cash-flow__drawer" title="流水导入" onClose={onClose}
      extra={<Tooltip title={LOCKED_TIP}><Button type="primary" disabled>上传文件</Button></Tooltip>}>
      {snapshot.isPending && <Typography.Text type="secondary">正在读取本地预览数据…</Typography.Text>}
      {snapshot.error && <EmptyState title="本地预览数据未就绪" description={(snapshot.error as Error).message} />}
      {snapshot.data && !item && <EmptyState title="没有流水导入的配置" description="imports.json 里没有「现金流账户报表」这一项" />}
      {item && (
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Alert type="info" showIcon message={item.node} description={snapshot.data?.meta.note} />
          <Descriptions className="fin-cash-flow__import-desc" size="small" column={1} bordered>
            <Descriptions.Item label="导入内容">{item.name}</Descriptions.Item>
            <Descriptions.Item label="交表人">财务专员</Descriptions.Item>
            <Descriptions.Item label="下一个交表节点">{item.next_node || "—"}</Descriptions.Item>
            <Descriptions.Item label="覆盖到">{item.cover ? <Tag bordered={false} color={item.stale ? "red" : "green"}>{item.cover}{item.stale ? " · 已过期" : ""}</Tag> : "—"}</Descriptions.Item>
            <Descriptions.Item label="接受类型">{item.accept}</Descriptions.Item>
            <Descriptions.Item label="文件名规则">{item.name_rule}</Descriptions.Item>
            <Descriptions.Item label="格式要求">{item.fmt}</Descriptions.Item>
            <Descriptions.Item label="用在">{item.used_in}</Descriptions.Item>
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
          <Typography.Text type="secondary">本地预览不能上传，按钮置灰；正式上传等流水导入的后端接口上线后开放。导入历史、失败记录以后也放在这里。</Typography.Text>
        </Space>
      )}
    </Drawer>
  );
}

export default ImportDrawer;

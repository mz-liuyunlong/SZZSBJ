/** Rule versions and the settings change log (read only). */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Drawer, Empty, Space, Typography } from "antd";
import { listRuleVersions, listSettingsChanges, settingsError, type RuleVersion, type SettingsChange } from "../settingsApi";
import { formatTime } from "./settingsShared";

const entityLabel: Record<string, string> = { rules: "规则", fc_region: "仓库地区", creation_defaults: "创建默认值" };

/** Versions + change log tables; used inline by the 版本与修改记录 tab and inside the drawer. */
export function RuleHistoryTables({ scope, enabled = true }: { scope: string; enabled?: boolean }) {
  const versions = useQuery({ queryKey: ["pmc-settings", scope, "versions"], queryFn: ({ signal }) => listRuleVersions(signal), retry: false, enabled });
  const changes = useQuery({ queryKey: ["pmc-settings", scope, "changes"], queryFn: ({ signal }) => listSettingsChanges(signal), retry: false, enabled });
  const versionColumns: ProColumns<RuleVersion>[] = [
    { title: "版本", key: "version_no", width: 70, render: (_, r) => `v${r.version_no}` },
    { title: "生效日", key: "effective_date", width: 110, render: (_, r) => r.effective_date },
    { title: "原因", key: "reason", render: (_, r) => r.reason },
    { title: "创建人", key: "created_by", width: 150, render: (_, r) => r.created_by },
  ];
  const changeColumns: ProColumns<SettingsChange>[] = [
    { title: "时间", key: "created_at", width: 150, render: (_, r) => formatTime(r.created_at) },
    { title: "对象", key: "entity", width: 150, render: (_, r) => `${entityLabel[r.entity] ?? r.entity} · ${r.entity_key}` },
    { title: "原因", key: "reason", render: (_, r) => r.reason },
    { title: "操作人", key: "actor", width: 120, render: (_, r) => r.actor },
  ];
  const table = <T extends object>(rows: T[], columns: ProColumns<T>[], rowKey: (r: T) => string, empty: string, loading: boolean) => (
    <ProTable<T>
      rowKey={rowKey}
      search={false}
      options={false}
      toolBarRender={false}
      size="small"
      bordered
      loading={loading}
      columns={columns}
      dataSource={rows}
      pagination={{ pageSize: 20, hideOnSinglePage: true, showTotal: (n) => `共 ${n} 条` }}
      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={empty} /> }}
    />
  );
  return (
      <Space direction="vertical" size={16} className="pmc-settings__drawer-stack">
        <Typography.Title level={5}>规则版本</Typography.Title>
        {versions.error && <Alert type="error" showIcon message={settingsError(versions.error)} action={<Button onClick={() => void versions.refetch()}>重试</Button>} />}
        {table(versions.data ?? [], versionColumns, (r) => String(r.version_no), "还没有规则版本", versions.isFetching)}
        <Typography.Title level={5}>修改记录</Typography.Title>
        {changes.error && <Alert type="error" showIcon message={settingsError(changes.error)} action={<Button onClick={() => void changes.refetch()}>重试</Button>} />}
        {table(changes.data?.items ?? [], changeColumns, (r) => `${r.entity}-${r.entity_key}-${r.created_at}`, "还没有修改记录", changes.isFetching)}
      </Space>
  );
}

export default function RuleHistoryDrawer({ open, scope, onClose }: { open: boolean; scope: string; onClose: () => void }) {
  return (
    <Drawer open={open} onClose={onClose} title="版本与修改记录" width={760}>
      <RuleHistoryTables scope={scope} enabled={open} />
    </Drawer>
  );
}

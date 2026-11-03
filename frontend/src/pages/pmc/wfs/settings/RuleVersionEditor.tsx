/** Edits the whole rule set and saves it as a new version (saving stays whole-version, PRP §5). */
import { EditableProTable, type ProColumns } from "@ant-design/pro-components";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Drawer, Space, message } from "antd";
import { useMemo, useState } from "react";
import { createRuleVersion, getRules, settingsError, type RuleRow } from "../settingsApi";
import SettingsReasonModal, { type ReasonAsk } from "./SettingsReasonModal";
import { today } from "./settingsShared";

type EditRow = RuleRow & { id: string };

const toRuleRow = ({ id, ...row }: EditRow): RuleRow => {
  void id;
  return { ...row, row_effective_date: String(row.row_effective_date).slice(0, 10) };
};

const blank = (id: string): EditRow => ({
  id, rule_key: null, node: "", region: "全部", carrier: "全部", channel: "全部", days: 0, remind_days: 0,
  row_effective_date: today(), notify: "", remark: "", decided: false,
});

export default function RuleVersionEditor({
  open, scope, canManage, onClose, onSaved,
}: { open: boolean; scope: string; canManage: boolean; onClose: () => void; onSaved: () => void }) {
  const full = useQuery({ queryKey: ["pmc-settings", scope, "rules-full"], queryFn: ({ signal }) => getRules(signal), retry: false, enabled: open });
  const loaded = useMemo(() => (full.data?.rows ?? []).map((r, i): EditRow => ({ ...r, id: `r${i}` })), [full.data]);
  // Unsaved edits live here; until the first edit the drawer shows the loaded version.
  const [edits, setRows] = useState<EditRow[]>();
  const rows = edits ?? loaded;
  const [ask, setAsk] = useState<ReasonAsk>();
  const close = () => { setRows(undefined); onClose(); };

  const columns: ProColumns<EditRow>[] = [
    { title: "节点", dataIndex: "node", width: 240, formItemProps: { rules: [{ required: true, message: "请填写节点" }] } },
    { title: "地区", dataIndex: "region", width: 90 },
    { title: "承运商", dataIndex: "carrier", width: 100 },
    { title: "渠道", dataIndex: "channel", width: 100 },
    { title: "天数", dataIndex: "days", valueType: "digit", width: 90, fieldProps: { min: 0, max: 365 } },
    { title: "提前提醒天数", dataIndex: "remind_days", valueType: "digit", width: 110, fieldProps: { min: 0, max: 365 } },
    { title: "生效日", dataIndex: "row_effective_date", valueType: "date", width: 130, fieldProps: { format: "YYYY-MM-DD" } },
    { title: "通知对象", dataIndex: "notify", width: 160 },
    { title: "备注", dataIndex: "remark", width: 260 },
    { title: "已确认", dataIndex: "decided", valueType: "switch", width: 80 },
  ];

  const save = () => setAsk({
    title: "保存为新规则版本",
    withDate: true,
    run: (reason, effective) => createRuleVersion({
      effective_date: effective ?? today(),
      reason,
      rows: rows.map(toRuleRow),
    }),
  });

  return (
    <Drawer
      open={open}
      onClose={close}
      title="编辑规则（保存为新版本）"
      width={1280}
      extra={(
        <Space>
          <Button onClick={close}>取消</Button>
          <Button type="primary" disabled={!canManage || rows.length === 0} onClick={save}>保存为新版本</Button>
        </Space>
      )}
    >
      {full.error && <Alert type="error" showIcon message={settingsError(full.error)} action={<Button onClick={() => void full.refetch()}>重试</Button>} />}
      <EditableProTable<EditRow>
        rowKey="id"
        size="small"
        bordered
        loading={full.isFetching}
        columns={columns}
        value={rows}
        onChange={(next) => setRows([...next])}
        scroll={{ x: 1360 }}
        recordCreatorProps={canManage ? { record: () => blank(`n${Date.now()}`), creatorButtonText: "新增规则" } : false}
        editable={{ type: "multiple", editableKeys: canManage ? rows.map((r) => r.id) : [], onValuesChange: (_, all) => setRows(all) }}
      />
      <SettingsReasonModal
        ask={ask}
        onClose={() => setAsk(undefined)}
        onSaved={() => { setAsk(undefined); setRows(undefined); onSaved(); }}
        onError={(e) => void message.error(settingsError(e))}
      />
    </Drawer>
  );
}

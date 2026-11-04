/** WFS 异常与提醒规则: rows of the version in force, server-side filter / sort / page. */
import type { ProColumns } from "@ant-design/pro-components";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Select, Space, Tag, message } from "antd";
import { useState } from "react";
import { StatusTagCell } from "@/components/report-table/cells";
import { RULE_SORTS, listRuleRows, settingsError, type RuleRow } from "../settingsApi";
import RuleHistoryDrawer from "./RuleHistoryDrawer";
import RuleVersionEditor from "./RuleVersionEditor";
import SettingsListLayout from "./SettingsListLayout";
import { SAMPLE_TAG, settingsAccess, type SectionProps } from "./settingsShared";
import { sortFromTable, useSettingsListState } from "./useSettingsListState";

type RuleSort = (typeof RULE_SORTS)[number];
type RuleItem = RuleRow & { id: string } & Record<string, unknown>;

export default function RuleSettingsSection({ page, scope, permissions }: SectionProps) {
  const qc = useQueryClient();
  const { canManage, writeHint } = settingsAccess(page, permissions);
  const list = useSettingsListState<{ region: string; decided: string }, RuleSort>("row_no");
  const query = {
    ...list.query,
    region: list.filters.region,
    decided: list.filters.decided === undefined ? undefined : list.filters.decided === "true",
  };
  const rows = useQuery({
    queryKey: ["pmc-settings", scope, "rule-rows", query],
    queryFn: ({ signal }) => listRuleRows(query, signal),
    retry: false,
  });
  const [historyOpen, setHistoryOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const data = rows.error ? undefined : rows.data;
  const sortOrder = (key: RuleSort) => (list.sort.by === key ? (list.sort.order === "desc" ? "descend" : "ascend") : null);

  const columns: ProColumns<RuleItem>[] = [
    { title: "节点", key: "node", width: 280, fixed: "left", sorter: true, sortOrder: sortOrder("node"), render: (_, r) => r.node },
    {
      title: "阈值状态", key: "decided", width: 110,
      render: (_, r) => (r.decided ? <StatusTagCell label="已确认" color="success" /> : <StatusTagCell label={SAMPLE_TAG} color="warning" />),
    },
    { title: "地区", key: "region", width: 90, render: (_, r) => r.region || "—" },
    { title: "承运商", key: "carrier", width: 100, render: (_, r) => r.carrier || "—" },
    { title: "渠道", key: "channel", width: 100, render: (_, r) => r.channel || "—" },
    { title: "天数", key: "days", width: 90, align: "right", sorter: true, sortOrder: sortOrder("days"), render: (_, r) => r.days },
    { title: "提前提醒天数", key: "remind_days", width: 120, align: "right", render: (_, r) => r.remind_days },
    {
      title: "生效日", key: "row_effective_date", width: 120, sorter: true, sortOrder: sortOrder("row_effective_date"),
      render: (_, r) => r.row_effective_date,
    },
    { title: "通知对象", key: "notify", width: 180, render: (_, r) => r.notify || "—" },
    { title: "备注", key: "remark", width: 320, render: (_, r) => r.remark || "—" },
  ];

  return (
    <SettingsListLayout<RuleItem>
      page={page}
      source={data ? `数据来自新系统数据库 · 版本 v${data.version.version_no} · 生效 ${data.version.effective_date}` : "数据来自新系统数据库"}
      loading={rows.isFetching}
      search={list.search}
      searchOptions={[{ value: "all", label: "全部" }, { value: "node", label: "节点" }, { value: "remark", label: "备注" }, { value: "notify", label: "通知对象" }]}
      searchPlaceholder="节点 / 备注 / 通知对象"
      onSearch={list.setSearch}
      onReset={list.reset}
      filters={(
        <>
          <Select allowClear aria-label="地区" className="report-filter-select" placeholder="地区（全部）"
            value={list.filters.region} onChange={(v?: string) => list.setFilter("region", v)}
            options={(data?.regions ?? []).map((v) => ({ value: v, label: v }))} />
          <Select allowClear aria-label="阈值状态" className="report-filter-select" placeholder="阈值状态（全部）"
            value={list.filters.decided} onChange={(v?: string) => list.setFilter("decided", v)}
            options={[{ value: "false", label: SAMPLE_TAG }, { value: "true", label: "已确认" }]} />
        </>
      )}
      alerts={(
        <>
          {rows.error && <Alert type="error" showIcon message={settingsError(rows.error)} action={<Button onClick={() => void rows.refetch()}>重试</Button>} />}
          {data && data.sample_rows > 0 && (
            <Alert type="warning" showIcon message={`有 ${data.sample_rows} 条规则按示例阈值执行（标「${SAMPLE_TAG}」），业务确认后改成正式值`} />
          )}
        </>
      )}
      summary={`异常与提醒规则（共 ${data?.total ?? "—"} 条）`}
      actions={(
        <Space wrap>
          {!canManage && <Tag>{writeHint}</Tag>}
          <Button onClick={() => setHistoryOpen(true)}>版本与修改记录</Button>
          <Button onClick={() => void rows.refetch()}>刷新</Button>
          <Button type="primary" disabled={!canManage} title={writeHint} onClick={() => setEditorOpen(true)}>编辑规则</Button>
        </Space>
      )}
      tableLabel="异常与提醒规则表格"
      rowKey="id"
      columns={columns}
      rows={(data?.items ?? []).map((r, i) => ({ ...r, id: `${r.rule_key ?? "row"}-${i}` }))}
      scrollX={1510}
      emptyText={rows.error ? "数据加载失败，请查看错误提示并重试" : "当前条件下暂无规则，可重置条件查看"}
      total={data?.total ?? 0}
      pagination={list.pagination}
      onPagination={list.setPagination}
      onSortChange={(sorter) => { const s = sortFromTable(sorter, RULE_SORTS, "row_no"); list.setSort(s.by, s.order); }}
      extra={(
        <>
          <RuleHistoryDrawer open={historyOpen} scope={scope} onClose={() => setHistoryOpen(false)} />
          <RuleVersionEditor
            open={editorOpen}
            scope={scope}
            canManage={canManage}
            onClose={() => setEditorOpen(false)}
            onSaved={() => {
              void message.success("已保存为新版本");
              setEditorOpen(false);
              void qc.invalidateQueries({ queryKey: ["pmc-settings", scope] });
            }}
          />
        </>
      )}
    />
  );
}

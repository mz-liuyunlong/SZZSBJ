/** WFS 仓库地区: FCs from the WFS board, server-side filter / sort / page. */
import type { ProColumns } from "@ant-design/pro-components";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Select, Space, Tag, message } from "antd";
import { useState } from "react";
import { StatusTagCell } from "@/components/report-table/cells";
import { FC_SORTS, REGIONS, listFcRegions, settingsError, updateFcRegion, type FcRegion, type Region } from "../settingsApi";
import SettingsListLayout from "./SettingsListLayout";
import SettingsReasonModal, { type ReasonAsk } from "./SettingsReasonModal";
import { formatTime, settingsAccess, type SectionProps } from "./settingsShared";
import { sortFromTable, useSettingsListState } from "./useSettingsListState";

type FcSort = (typeof FC_SORTS)[number];
type FcItem = FcRegion & Record<string, unknown>;

export default function FcRegionsSection({ page, scope, permissions }: SectionProps) {
  const qc = useQueryClient();
  const { canManage, writeHint } = settingsAccess(page, permissions);
  const list = useSettingsListState<{ region: string; state: string }, FcSort>("fc");
  const query = { ...list.query, region: list.filters.region as Region | undefined, state: list.filters.state };
  const fcs = useQuery({
    queryKey: ["pmc-settings", scope, "fc", query],
    queryFn: ({ signal }) => listFcRegions(query, signal),
    retry: false,
  });
  const [ask, setAsk] = useState<ReasonAsk>();
  const data = fcs.error ? undefined : fcs.data;
  const sortOrder = (key: FcSort) => (list.sort.by === key ? (list.sort.order === "desc" ? "descend" : "ascend") : null);

  const columns: ProColumns<FcItem>[] = [
    { title: "仓库 (FC)", key: "fc", width: 110, fixed: "left", sorter: true, sortOrder: sortOrder("fc"), render: (_, r) => r.fc },
    { title: "邮编", key: "zip", width: 90, sorter: true, sortOrder: sortOrder("zip"), render: (_, r) => r.zip ?? "—" },
    { title: "地址全称", key: "address", width: 400, render: (_, r) => r.address ?? "—" },
    { title: "州", key: "state", width: 80, sorter: true, sortOrder: sortOrder("state"), render: (_, r) => r.state ?? "—" },
    {
      title: "地区", key: "region", width: 120,
      render: (_, r) => (
        <Select<Region>
          size="small"
          aria-label={`${r.fc} 地区`}
          value={r.region}
          disabled={!canManage}
          className="pmc-settings__region"
          options={REGIONS.map((x) => ({ value: x, label: x }))}
          onChange={(region) => setAsk({ title: `${r.fc} 改为 ${region}`, run: (reason) => updateFcRegion(r.fc, { region, name: r.name, reason }) })}
        />
      ),
    },
    {
      title: "地区来源", key: "region_source", width: 100,
      render: (_, r) => (r.region_source === "saved" ? <StatusTagCell label="已保存" color="processing" /> : <StatusTagCell label="按州默认" color="default" />),
    },
    { title: "货件数", key: "shipments", width: 90, align: "right", sorter: true, sortOrder: sortOrder("shipments"), render: (_, r) => r.shipments },
    { title: "最近修改", key: "updated", width: 180, render: (_, r) => (r.updated_by ? `${r.updated_by} · ${formatTime(r.updated_at)}` : "—") },
  ];

  return (
    <SettingsListLayout<FcItem>
      page={page}
      source="数据来自新系统数据库 · 仓库来自 WFS 货件看板的收货地址"
      loading={fcs.isFetching}
      search={list.search}
      searchOptions={[{ value: "all", label: "全部" }, { value: "fc", label: "仓库" }, { value: "zip", label: "邮编" }, { value: "address", label: "地址" }]}
      searchPlaceholder="仓库 / 邮编 / 地址"
      onSearch={list.setSearch}
      onReset={list.reset}
      filters={(
        <>
          <Select allowClear aria-label="地区" className="report-filter-select" placeholder="地区（全部）"
            value={list.filters.region} onChange={(v?: string) => list.setFilter("region", v)}
            options={REGIONS.map((x) => ({ value: x, label: x }))} />
          <Select allowClear showSearch aria-label="州" className="report-filter-select" placeholder="州（全部）"
            value={list.filters.state} onChange={(v?: string) => list.setFilter("state", v)}
            options={(data?.states ?? []).map((v) => ({ value: v, label: v }))} />
        </>
      )}
      alerts={fcs.error && <Alert type="error" showIcon message={settingsError(fcs.error)} action={<Button onClick={() => void fcs.refetch()}>重试</Button>} />}
      summary={`仓库地区（共 ${data?.total ?? "—"} 个仓库；未保存的按所在州给默认地区）`}
      actions={(
        <Space wrap>
          {!canManage && <Tag>{writeHint}</Tag>}
          <Button onClick={() => void fcs.refetch()}>刷新</Button>
        </Space>
      )}
      tableLabel="仓库地区表格"
      rowKey="fc"
      columns={columns}
      rows={(data?.items ?? []) as FcItem[]}
      scrollX={1170}
      emptyText={fcs.error ? "数据加载失败，请查看错误提示并重试" : "当前条件下暂无仓库，可重置条件查看"}
      total={data?.total ?? 0}
      pagination={list.pagination}
      onPagination={list.setPagination}
      onSortChange={(sorter) => { const s = sortFromTable(sorter, FC_SORTS, "fc"); list.setSort(s.by, s.order); }}
      extra={(
        <SettingsReasonModal
          ask={ask}
          onClose={() => setAsk(undefined)}
          onSaved={() => { setAsk(undefined); void message.success("已保存"); void qc.invalidateQueries({ queryKey: ["pmc-settings", scope] }); }}
          onError={(e) => void message.error(settingsError(e))}
        />
      )}
    />
  );
}

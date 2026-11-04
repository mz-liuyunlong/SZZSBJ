/** 物流渠道字典 (PMC-wide, read only): Lingxing channel file, server-side filter / sort / page. */
import type { ProColumns } from "@ant-design/pro-components";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Select } from "antd";
import { StatusTagCell } from "@/components/report-table/cells";
import { CHANNEL_SORTS, listLogisticsChannels, settingsError, type LogisticsChannel } from "../settingsApi";
import SettingsListLayout from "./SettingsListLayout";
import type { SectionProps } from "./settingsShared";
import { sortFromTable, useSettingsListState } from "./useSettingsListState";

type ChannelSort = (typeof CHANNEL_SORTS)[number];
type ChannelItem = LogisticsChannel & Record<string, unknown>;

export default function LogisticsChannelsSection({ page, scope }: SectionProps) {
  const list = useSettingsListState<{ provider: string; method: string; enabled: string }, ChannelSort>("provider_name");
  const query = {
    ...list.query,
    provider: list.filters.provider,
    method: list.filters.method,
    enabled: list.filters.enabled === undefined ? undefined : list.filters.enabled === "true",
  };
  const channels = useQuery({
    queryKey: ["pmc-settings", scope, "channels", query],
    queryFn: ({ signal }) => listLogisticsChannels(query, signal),
    retry: false,
  });
  const data = channels.error ? undefined : channels.data;
  const sortOrder = (key: ChannelSort) => (list.sort.by === key ? (list.sort.order === "desc" ? "descend" : "ascend") : null);
  const notLoaded = data && !data.loaded;

  const columns: ProColumns<ChannelItem>[] = [
    { title: "渠道编号（领星）", key: "channel_id", width: 140, fixed: "left", sorter: true, sortOrder: sortOrder("channel_id"), render: (_, r) => r.channel_id },
    { title: "渠道", key: "channel_name", width: 280, sorter: true, sortOrder: sortOrder("channel_name"), render: (_, r) => r.channel_name ?? "—" },
    { title: "物流商编号（领星）", key: "provider_id", width: 150, render: (_, r) => r.provider_id ?? "—" },
    { title: "物流商", key: "provider_name", width: 280, sorter: true, sortOrder: sortOrder("provider_name"), render: (_, r) => r.provider_name ?? "—" },
    { title: "运输方式", key: "method_name", width: 120, render: (_, r) => r.method_name ?? "—" },
    { title: "状态", key: "enabled", width: 90, render: (_, r) => (r.enabled ? <StatusTagCell label="启用" color="success" /> : <StatusTagCell label="停用" color="default" />) },
  ];

  return (
    <SettingsListLayout<ChannelItem>
      page={page}
      source="只读 · 来自领星物流渠道文件，本页不调用领星"
      loading={channels.isFetching}
      search={list.search}
      searchOptions={[{ value: "all", label: "全部" }, { value: "channel_id", label: "渠道编号" }, { value: "channel_name", label: "渠道" }, { value: "provider", label: "物流商" }]}
      searchPlaceholder="渠道编号 / 渠道 / 物流商"
      onSearch={list.setSearch}
      onReset={list.reset}
      filters={(
        <>
          <Select allowClear showSearch aria-label="物流商" className="report-filter-select" placeholder="物流商（全部）"
            value={list.filters.provider} onChange={(v?: string) => list.setFilter("provider", v)}
            options={(data?.providers ?? []).map((v) => ({ value: v, label: v }))} popupMatchSelectWidth={false} />
          <Select allowClear aria-label="运输方式" className="report-filter-select" placeholder="运输方式（全部）"
            value={list.filters.method} onChange={(v?: string) => list.setFilter("method", v)}
            options={(data?.methods ?? []).map((v) => ({ value: v, label: v }))} />
          <Select allowClear aria-label="状态" className="report-filter-select" placeholder="状态（全部）"
            value={list.filters.enabled} onChange={(v?: string) => list.setFilter("enabled", v)}
            options={[{ value: "true", label: "启用" }, { value: "false", label: "停用" }]} />
        </>
      )}
      alerts={channels.error && <Alert type="error" showIcon message={settingsError(channels.error)} action={<Button onClick={() => void channels.refetch()}>重试</Button>} />}
      summary={`物流渠道（共 ${data?.total ?? "—"} 条）`}
      actions={<Button onClick={() => void channels.refetch()}>刷新</Button>}
      tableLabel="物流渠道字典表格"
      rowKey="channel_id"
      columns={columns}
      rows={(data?.items ?? []) as ChannelItem[]}
      scrollX={1060}
      emptyText={channels.error ? "数据加载失败，请查看错误提示并重试" : notLoaded ? "尚未导入物流渠道文件，导入后在这里显示" : "当前条件下暂无渠道，可重置条件查看"}
      total={data?.total ?? 0}
      pagination={list.pagination}
      onPagination={list.setPagination}
      onSortChange={(sorter) => { const s = sortFromTable(sorter, CHANNEL_SORTS, "provider_name"); list.setSort(s.by, s.order); }}
    />
  );
}

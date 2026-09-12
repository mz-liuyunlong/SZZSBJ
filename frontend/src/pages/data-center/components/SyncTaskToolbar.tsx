import { ReloadOutlined } from "@ant-design/icons";
import { Button, Card, Select } from "antd";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import type {
  SyncTaskFilters,
  SyncTaskModule,
  SyncTaskStatus,
} from "@/pages/data-center/syncTaskTypes";

interface SyncTaskToolbarProps {
  filters: SyncTaskFilters;
  modules: SyncTaskModule[];
  statuses: SyncTaskStatus[];
  onChange: (filters: SyncTaskFilters) => void;
  onReset: () => void;
  onRefresh: () => void;
}

function SyncTaskToolbar({
  filters,
  modules,
  statuses,
  onChange,
  onReset,
  onRefresh,
}: SyncTaskToolbarProps) {
  const update = <Key extends keyof SyncTaskFilters>(key: Key, value: SyncTaskFilters[Key]) => {
    onChange({ ...filters, [key]: value, anomalyOnly: key === "status" ? false : filters.anomalyOnly });
  };

  return (
    <Card size="small" className="sync-task__toolbar-card">
      <div className="sync-task__toolbar" role="search" aria-label="同步任务筛选">
        <Select
          allowClear
          className="report-filter-select sync-task__filter-select"
          classNames={{ popup: { root: "report-filter-select-dropdown" } }}
          aria-label="模块"
          placeholder="全部模块"
          value={filters.module}
          options={modules.map((module) => ({ label: module, value: module }))}
          onChange={(value) => update("module", value)}
        />
        <Select
          allowClear
          className="report-filter-select sync-task__filter-select"
          classNames={{ popup: { root: "report-filter-select-dropdown" } }}
          aria-label="同步状态"
          placeholder="全部同步状态"
          value={filters.status}
          options={statuses.map((status) => ({ label: status, value: status }))}
          onChange={(value) => update("status", value)}
        />
        <Select
          allowClear
          className="report-filter-select sync-task__filter-select sync-task__filter-select--wide"
          classNames={{ popup: { root: "report-filter-select-dropdown" } }}
          aria-label="自动同步状态"
          placeholder="全部自动同步状态"
          value={filters.autoSync}
          options={[
            { label: "已开启", value: "on" },
            { label: "已关闭", value: "off" },
          ]}
          onChange={(value) => update("autoSync", value)}
        />
        <ConnectedSearch
          className="sync-task__search"
          typeAriaLabel="搜索类型"
          typeOptions={[{ label: "任务", value: "task" }]}
          typeValue="task"
          inputAriaLabel="搜索同步任务"
          inputPlaceholder="搜索任务名称 / 接口名称 / 模块"
          inputValue={filters.keyword}
          searchAriaLabel="搜索同步任务"
          onTypeChange={() => undefined}
          onInputChange={(keyword) => update("keyword", keyword)}
          onSearch={() => onChange({ ...filters, anomalyOnly: false })}
        />
        <ResetButton onClick={onReset} />
        <Button icon={<ReloadOutlined aria-hidden="true" />} onClick={onRefresh}>
          刷新
        </Button>
      </div>
    </Card>
  );
}

export default SyncTaskToolbar;

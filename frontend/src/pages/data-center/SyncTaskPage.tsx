import { CalendarOutlined } from "@ant-design/icons";
import { Button, Modal, Typography, message } from "antd";
import dayjs from "dayjs";
import { useMemo, useState, type Key } from "react";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import SyncTaskConfigDrawer from "@/pages/data-center/components/SyncTaskConfigDrawer";
import SyncTaskLogDrawer from "@/pages/data-center/components/SyncTaskLogDrawer";
import SyncTaskScheduleDrawer from "@/pages/data-center/components/SyncTaskScheduleDrawer";
import SyncTaskSummaryCards from "@/pages/data-center/components/SyncTaskSummaryCards";
import SyncTaskTable from "@/pages/data-center/components/SyncTaskTable";
import SyncTaskToolbar from "@/pages/data-center/components/SyncTaskToolbar";
import {
  dayScheduleItems,
  syncTaskLogs,
  syncTaskModules,
  syncTaskRows,
  syncTaskStatuses,
  weekScheduleItems,
} from "@/pages/data-center/syncTaskMockData";
import type {
  SyncScheduleTab,
  SyncTaskFilters,
  SyncTaskRow,
  SyncTaskStatus,
} from "@/pages/data-center/syncTaskTypes";
import "@/pages/data-center/SyncTaskPage.css";

const anomalyStatuses = new Set<SyncTaskStatus>(["失败", "超时", "部分成功"]);

const createInitialFilters = (): SyncTaskFilters => ({
  keyword: "",
});

const formatNow = () => dayjs().format("YYYY-MM-DD HH:mm");

const defaultColumnWidths: Record<string, number> = {
  taskName: 190,
  module: 96,
  autoSync: 104,
  frequency: 128,
  nextRunAt: 168,
  lastStatus: 128,
  lastRunAt: 168,
  todayResult: 136,
  actions: 178,
};

interface SyncTaskPageProps {
  page: NavigationPage;
}

function SyncTaskPage({ page }: SyncTaskPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [rows, setRows] = useState<SyncTaskRow[]>(syncTaskRows);
  const [filters, setFilters] = useState(createInitialFilters);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [columnWidths, setColumnWidths] = useState(defaultColumnWidths);
  const [configTask, setConfigTask] = useState<SyncTaskRow>();
  const [logTask, setLogTask] = useState<SyncTaskRow>();
  const [logOpen, setLogOpen] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleInitialTab, setScheduleInitialTab] = useState<SyncScheduleTab>("day");
  const [syncCandidate, setSyncCandidate] = useState<{
    task: SyncTaskRow;
    mode: "sync" | "retry";
  }>();
  const [disableCandidate, setDisableCandidate] = useState<SyncTaskRow>();

  const filteredRows = useMemo(() => {
    const keyword = filters.keyword.trim().toLocaleLowerCase();

    return rows.filter((row) => {
      const keywordTarget = `${row.taskName}${row.interfaceName}${row.module}${row.lastStatus}`.toLocaleLowerCase();
      return (
        (!filters.module || row.module === filters.module)
        && (!filters.status || row.lastStatus === filters.status)
        && (!filters.autoSync || (filters.autoSync === "on" ? row.autoSync : !row.autoSync))
        && (!filters.anomalyOnly || anomalyStatuses.has(row.lastStatus))
        && (!keyword || keywordTarget.includes(keyword))
      );
    });
  }, [filters, rows]);

  const updateRows = (task: SyncTaskRow) => {
    setRows((currentRows) => currentRows.map((row) => (row.id === task.id ? task : row)));
  };

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const updateFilters = (nextFilters: SyncTaskFilters) => {
    setFilters(nextFilters);
    resetPageAndSelection();
  };

  const resetFilters = () => {
    setFilters(createInitialFilters());
    resetPageAndSelection();
  };

  const openSchedule = (tab: SyncScheduleTab) => {
    setScheduleInitialTab(tab);
    setScheduleOpen(true);
  };

  const openLogDrawer = (task?: SyncTaskRow) => {
    setLogTask(task);
    setLogOpen(true);
  };

  const requestManualSync = (task: SyncTaskRow) => {
    if (task.lastStatus === "运行中") {
      void messageApi.warning("任务运行中，不可重复触发");
      return;
    }
    setSyncCandidate({ task, mode: "sync" });
  };

  const requestRetry = (task: SyncTaskRow) => {
    if (task.lastStatus === "运行中") {
      void messageApi.warning("任务运行中，不可重复触发");
      return;
    }
    setSyncCandidate({ task, mode: "retry" });
  };

  const confirmSync = () => {
    if (!syncCandidate) return;
    updateRows({
      ...syncCandidate.task,
      lastStatus: "运行中",
      lastRunAt: formatNow(),
    });
    setSyncCandidate(undefined);
    void messageApi.success(syncCandidate.mode === "retry" ? "已创建失败重试任务" : "已创建手动同步任务");
  };

  const toggleAutoSync = (task: SyncTaskRow, checked: boolean) => {
    if (checked) {
      updateRows({
        ...task,
        autoSync: true,
        lastStatus: task.lastStatus === "已停用" ? "成功" : task.lastStatus,
        nextRunAt: task.nextRunAt ?? "2026-09-13 00:00",
      });
      void messageApi.success("自动同步已开启");
      return;
    }
    setDisableCandidate(task);
  };

  const confirmDisable = () => {
    if (!disableCandidate) return;
    updateRows({
      ...disableCandidate,
      autoSync: false,
      lastStatus: "已停用",
      nextRunAt: undefined,
    });
    setDisableCandidate(undefined);
    void messageApi.success("自动同步已关闭");
  };

  const saveConfig = (task: SyncTaskRow) => {
    updateRows(task);
    setConfigTask(undefined);
    void messageApi.success("配置已保存");
  };

  const refreshTasks = () => {
    void messageApi.success("任务列表已刷新");
  };

  const bulkAction = () => {
    void messageApi.info(selectedRowKeys.length > 0 ? "批量操作接口待接入" : "请先勾选任务");
  };

  return (
    <PageShell page={page}>
      {messageContextHolder}
      <div className="sync-task">
        <section className="sync-task__hero">
          <div className="sync-task__hero-main">
            <div className="sync-task__hero-copy">
              <Typography.Title level={3} className="sync-task__hero-title">
                同步任务管理
              </Typography.Title>
              <Typography.Text className="sync-task__hero-description" type="secondary">
                集中管理平台、ERP、广告、财务等接口同步任务，支持自动同步、失败重试、日/周计划与日志追踪。
              </Typography.Text>
            </div>
            <Button type="primary" icon={<CalendarOutlined aria-hidden="true" />} onClick={() => openSchedule("day")}>
              同步日程
            </Button>
          </div>
        </section>

        <section className="sync-task__card">
          <div className="sync-task__card-head">
            <div>
              <span className="sync-task__card-title">任务总控</span>
              <span className="sync-task__card-sub">按任务配置维度管理同步状态</span>
            </div>
          </div>
          <SyncTaskToolbar
            filters={filters}
            modules={syncTaskModules}
            statuses={syncTaskStatuses}
            onChange={updateFilters}
            onReset={resetFilters}
            onRefresh={refreshTasks}
          />
          <SyncTaskSummaryCards rows={filteredRows} />
          <SyncTaskTable
            rows={filteredRows}
            columnWidths={columnWidths}
            selectedRowKeys={selectedRowKeys}
            currentPage={currentPage}
            pageSize={pageSize}
            onCurrentPageChange={setCurrentPage}
            onColumnWidthChange={(key, width) => setColumnWidths((current) => ({
              ...current,
              [key]: width,
            }))}
            onPageSizeChange={(nextPageSize) => {
              setPageSize(nextPageSize);
              resetPageAndSelection();
            }}
            onSelectionChange={setSelectedRowKeys}
            onOpenConfig={setConfigTask}
            onOpenLog={openLogDrawer}
            onRequestSync={requestManualSync}
            onRequestRetry={requestRetry}
            onToggleAutoSync={toggleAutoSync}
            onBulkAction={bulkAction}
          />
        </section>
      </div>

      <SyncTaskConfigDrawer
        open={Boolean(configTask)}
        task={configTask}
        modules={syncTaskModules}
        onClose={() => setConfigTask(undefined)}
        onSave={saveConfig}
      />
      <SyncTaskLogDrawer
        open={logOpen}
        task={logTask}
        logs={syncTaskLogs}
        onClose={() => setLogOpen(false)}
      />
      <SyncTaskScheduleDrawer
        open={scheduleOpen}
        initialTab={scheduleInitialTab}
        dayItems={dayScheduleItems}
        weekItems={weekScheduleItems}
        onClose={() => setScheduleOpen(false)}
        onOpenGlobalLog={() => {
          setScheduleOpen(false);
          openLogDrawer(undefined);
        }}
      />
      <Modal
        title={syncCandidate?.mode === "retry" ? "重试同步确认" : "立即同步确认"}
        open={Boolean(syncCandidate)}
        okText={syncCandidate?.mode === "retry" ? "确认重试" : "确认同步"}
        cancelText="取消"
        onOk={confirmSync}
        onCancel={() => setSyncCandidate(undefined)}
      >
        <div className="sync-task__modal-warn">
          该任务可能正在处理较大数据量。确认后会立即创建一次{syncCandidate?.mode === "retry" ? "失败重试" : "手动同步"}任务。
        </div>
        <Typography.Paragraph>
          是否立即执行：{syncCandidate?.task.taskName}？
        </Typography.Paragraph>
      </Modal>
      <Modal
        title="关闭自动同步？"
        open={Boolean(disableCandidate)}
        okText="确认关闭"
        cancelText="取消"
        onOk={confirmDisable}
        onCancel={() => setDisableCandidate(undefined)}
      >
        <Typography.Paragraph>
          关闭后，系统将不再按照计划自动执行该任务，但仍可手动点击“立即同步”。
        </Typography.Paragraph>
      </Modal>
    </PageShell>
  );
}

export default SyncTaskPage;

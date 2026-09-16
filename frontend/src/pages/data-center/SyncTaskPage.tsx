import { CalendarOutlined } from "@ant-design/icons";
import { Button, Input, Modal, Spin, Typography, message } from "antd";
import { useEffect, useMemo, useRef, type Key } from "react";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import SyncTaskConfigDrawer, { type SyncTaskConfigFormValues } from "@/pages/data-center/components/SyncTaskConfigDrawer";
import SyncTaskLogDrawer from "@/pages/data-center/components/SyncTaskLogDrawer";
import SyncTaskScheduleDrawer from "@/pages/data-center/components/SyncTaskScheduleDrawer";
import SyncTaskSummaryCards from "@/pages/data-center/components/SyncTaskSummaryCards";
import SyncTaskTable from "@/pages/data-center/components/SyncTaskTable";
import SyncTaskToolbar from "@/pages/data-center/components/SyncTaskToolbar";
import {
  useCreateIntegrationSyncManualRunMutation,
  useIntegrationSyncTasksQuery,
  useRetryIntegrationSyncRunMutation,
  useUpdateIntegrationSyncConfigMutation,
} from "@/pages/data-center/integrationSyncTaskQueries";
import {
  getAutoSyncGuard,
  getManualSyncGuard,
  getRetryGuard,
  getSaveConfigGuard,
} from "@/pages/data-center/syncTaskOperationGuards";
import { formatSyncTaskOperationError } from "@/pages/data-center/syncTaskOperationMessages";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import { useElementScrollRestoration } from "@/shared/page-state/useElementScrollRestoration";
import type {
  SyncScheduleItem,
  SyncScheduleTab,
  SyncTaskFilters,
  SyncTaskLog,
  SyncTaskRow,
  SyncTaskStatus,
} from "@/pages/data-center/syncTaskTypes";
import "@/pages/data-center/SyncTaskPage.css";

const anomalyStatuses = new Set<SyncTaskStatus>(["失败", "超时", "部分成功"]);

const createInitialFilters = (): SyncTaskFilters => ({
  keyword: "",
});

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

interface SyncTaskOverview {
  rows: SyncTaskRow[];
  logs: SyncTaskLog[];
  schedules: SyncScheduleItem[];
}

const emptySyncTaskOverview: SyncTaskOverview = {
  rows: [],
  logs: [],
  schedules: [],
};


const weekDayMap: Record<string, number> = {
  周一: 1,
  周二: 2,
  周三: 3,
  周四: 4,
  周五: 5,
  周六: 6,
  周日: 0,
};

const parseTime = (value?: string) => {
  const match = value?.trim().match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return { hour, minute };
};

const buildScheduleCron = (values: SyncTaskConfigFormValues) => {
  if (!values.autoSync || values.cycle === "手动任务") return null;
  const firstTime = parseTime(values.runTimes?.[0]);
  if (!firstTime) return null;
  if (values.cycle === "周任务") {
    const days = values.weekDays?.map((day) => weekDayMap[day]).filter((day) => day !== undefined);
    if (!days || days.length === 0) return null;
    return `${firstTime.minute} ${firstTime.hour} * * ${days.join(",")}`;
  }
  return `${firstTime.minute} ${firstTime.hour} * * *`;
};

const buildConfigPayload = (values: SyncTaskConfigFormValues) => {
  const scheduleCron = buildScheduleCron(values);
  return {
    schedule_enabled: Boolean(values.autoSync && scheduleCron),
    schedule_cron: scheduleCron,
    max_attempts: values.retryEnabled ? Math.max((values.retryTimes ?? 0) + 1, 1) : 1,
  };
};

interface SyncTaskPageProps {
  page: NavigationPage;
}

function SyncTaskPage({ page }: SyncTaskPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [modalApi, modalContextHolder] = Modal.useModal();
  const messageApiRef = useRef(messageApi);
  const pageStateKey = `sync-task:${page.key}`;
  const syncTaskPageRootRef = useRef<HTMLDivElement | null>(null);
  const shownErrorsRef = useRef(new Set<string>());
  const [filters, setFilters] = usePageStateCache(`${pageStateKey}:filters`, createInitialFilters);
  const [currentPage, setCurrentPage] = usePageStateCache(`${pageStateKey}:currentPage`, 1);
  const [pageSize, setPageSize] = usePageStateCache(`${pageStateKey}:pageSize`, 50);
  const [selectedRowKeys, setSelectedRowKeys] = usePageStateCache<Key[]>(`${pageStateKey}:selectedRowKeys`, []);
  const [columnWidths, setColumnWidths] = usePageStateCache(`${pageStateKey}:columnWidths`, defaultColumnWidths);
  const [configTask, setConfigTask] = usePageStateCache<SyncTaskRow | undefined>(`${pageStateKey}:configTask`, undefined);
  const [logTask, setLogTask] = usePageStateCache<SyncTaskRow | undefined>(`${pageStateKey}:logTask`, undefined);
  const [logOpen, setLogOpen] = usePageStateCache(`${pageStateKey}:logOpen`, false);
  const [scheduleOpen, setScheduleOpen] = usePageStateCache(`${pageStateKey}:scheduleOpen`, false);
  const [scheduleInitialTab, setScheduleInitialTab] = usePageStateCache<SyncScheduleTab>(`${pageStateKey}:scheduleInitialTab`, "day");

  useElementScrollRestoration(`${pageStateKey}:tableScroll`, syncTaskPageRootRef, ".ant-table-body");
  const tasksQuery = useIntegrationSyncTasksQuery();
  const manualRunMutation = useCreateIntegrationSyncManualRunMutation();
  const retryRunMutation = useRetryIntegrationSyncRunMutation();
  const updateConfigMutation = useUpdateIntegrationSyncConfigMutation();
  const syncTaskOverview = tasksQuery.data ?? emptySyncTaskOverview;
  const rows = syncTaskOverview.rows;
  const logs = syncTaskOverview.logs;
  const scheduleItems = syncTaskOverview.schedules;

  useEffect(() => {
    messageApiRef.current = messageApi;
  }, [messageApi]);

  useEffect(() => {
    if (!tasksQuery.error) return;
    const text = tasksQuery.error instanceof Error
      ? tasksQuery.error.message
      : "BACKEND_REQUEST_FAILED";
    if (shownErrorsRef.current.has(text)) return;
    shownErrorsRef.current.add(text);
    void messageApiRef.current.error(text);
  }, [tasksQuery.error]);

  const syncTaskModules = useMemo(() => Array.from(new Set(rows.map((row) => row.module))), [rows]);
  const syncTaskStatuses: SyncTaskStatus[] = ["成功", "失败", "运行中", "部分成功", "超时", "已停用"];

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
    const operationGuard = getManualSyncGuard(task);
    if (!operationGuard.allowed || !task.configId) {
      void messageApi.warning(operationGuard.reason);
      return;
    }

    let reason = `手动触发同步：${task.taskName}`;
    modalApi.confirm({
      title: operationGuard.confirmTitle,
      content: (
        <div>
          <Typography.Paragraph>{operationGuard.confirmDescription}</Typography.Paragraph>
          <Typography.Paragraph type="secondary">
            任务：{task.taskName}；接口：{task.interfaceName}
          </Typography.Paragraph>
          <Input.TextArea
            defaultValue={reason}
            rows={3}
            maxLength={1000}
            showCount
            onChange={(event) => { reason = event.target.value; }}
          />
        </div>
      ),
      okText: "确认执行",
      cancelText: "取消",
      onOk: async () => {
        try {
          await manualRunMutation.mutateAsync({ configId: task.configId!, reason });
          void messageApi.success("已创建同步任务");
        } catch (reason_) {
          void messageApi.error(formatSyncTaskOperationError(reason_));
        }
      },
    });
  };

  const requestRetry = (task: SyncTaskRow) => {
    const operationGuard = getRetryGuard(task);
    if (!operationGuard.allowed || !task.latestRunId) {
      void messageApi.warning(operationGuard.reason);
      return;
    }

    let reason = `重试同步任务：${task.taskName}`;
    modalApi.confirm({
      title: operationGuard.confirmTitle,
      content: (
        <div>
          <Typography.Paragraph>{operationGuard.confirmDescription}</Typography.Paragraph>
          <Typography.Paragraph type="secondary">
            最近状态：{task.lastStatus}；最近错误：{task.errorCode ?? "-"}
          </Typography.Paragraph>
          <Input.TextArea
            defaultValue={reason}
            rows={3}
            maxLength={1000}
            showCount
            onChange={(event) => { reason = event.target.value; }}
          />
        </div>
      ),
      okText: "确认重试",
      cancelText: "取消",
      onOk: async () => {
        try {
          await retryRunMutation.mutateAsync({ runId: task.latestRunId!, reason });
          void messageApi.success("已创建重试任务");
        } catch (reason_) {
          void messageApi.error(formatSyncTaskOperationError(reason_));
        }
      },
    });
  };

  const toggleAutoSync = (task: SyncTaskRow, checked: boolean) => {
    const operationGuard = getAutoSyncGuard(task, checked);
    if (!operationGuard.allowed || !task.configId) {
      if (checked && task.configId && !task.scheduleCron) {
        setConfigTask(task);
      }
      void messageApi.warning(operationGuard.reason);
      return;
    }

    modalApi.confirm({
      title: operationGuard.confirmTitle,
      content: (
        <div>
          <Typography.Paragraph>{operationGuard.confirmDescription}</Typography.Paragraph>
          <Typography.Paragraph type="secondary">
            任务：{task.taskName}；当前计划：{task.frequency}
          </Typography.Paragraph>
        </div>
      ),
      okText: "确认修改",
      cancelText: "取消",
      onOk: async () => {
        try {
          await updateConfigMutation.mutateAsync({
            configId: task.configId!,
            payload: checked
              ? {
                  schedule_enabled: true,
                  schedule_cron: task.scheduleCron,
                }
              : {
                  schedule_enabled: false,
                },
          });
          void messageApi.success(checked ? "已开启自动同步" : "已关闭自动同步");
        } catch (reason_) {
          void messageApi.error(formatSyncTaskOperationError(reason_));
        }
      },
    });
  };

  const saveConfig = (task: SyncTaskRow, values: SyncTaskConfigFormValues) => {
    const operationGuard = getSaveConfigGuard(task);
    if (!operationGuard.allowed || !task.configId) {
      void messageApi.warning(operationGuard.reason);
      return;
    }

    const payload = buildConfigPayload(values);
    if (values.autoSync && !payload.schedule_cron) {
      void messageApi.warning("开启自动同步需要至少一个有效执行时间，例如 08:00");
      return;
    }

    modalApi.confirm({
      title: operationGuard.confirmTitle,
      content: (
        <div>
          <Typography.Paragraph>{operationGuard.confirmDescription}</Typography.Paragraph>
          <Typography.Paragraph type="secondary">
            任务：{task.taskName}；自动同步：{payload.schedule_enabled ? "开启" : "关闭"}；cron：{payload.schedule_cron ?? "-"}
          </Typography.Paragraph>
        </div>
      ),
      okText: "确认保存",
      cancelText: "取消",
      onOk: async () => {
        try {
          await updateConfigMutation.mutateAsync({ configId: task.configId!, payload });
          setConfigTask(undefined);
          void messageApi.success("同步配置已保存");
        } catch (reason_) {
          void messageApi.error(formatSyncTaskOperationError(reason_));
        }
      },
    });
  };

  const refreshTasks = () => {
    void tasksQuery.refetch();
  };

  const bulkAction = () => {
    void messageApi.info(selectedRowKeys.length > 0 ? "批量操作接口待接入" : "请先勾选任务");
  };

  return (
    <PageShell page={page}>
      {messageContextHolder}
      {modalContextHolder}
      <div ref={syncTaskPageRootRef} className="sync-task">
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
          {tasksQuery.isPending && (
        <span className="sync-task__loading" role="status">
          <Spin size="small" />
          <span>正在加载同步任务</span>
        </span>
      )}
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
        logs={logs}
        onClose={() => setLogOpen(false)}
      />
      <SyncTaskScheduleDrawer
        open={scheduleOpen}
        initialTab={scheduleInitialTab}
        dayItems={scheduleItems}
        weekItems={scheduleItems}
        onClose={() => setScheduleOpen(false)}
        onOpenGlobalLog={() => {
          setScheduleOpen(false);
          openLogDrawer(undefined);
        }}
      />
    </PageShell>
  );
}

export default SyncTaskPage;

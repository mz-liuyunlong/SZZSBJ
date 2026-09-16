import {
  Alert,
  Button,
  DatePicker,
  Drawer,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  type TableColumnsType,
} from "antd";
import { useMemo, useState } from "react";
import {
  useIntegrationSyncRunRawRequestRefsQuery,
  useIntegrationSyncRunWorkItemsQuery,
} from "@/pages/data-center/integrationSyncTaskQueries";
import type {
  SyncTaskLog,
  SyncTaskRawRequestRef,
  SyncTaskRow,
  SyncTaskStatus,
  SyncTaskTriggerType,
  SyncTaskWorkItem,
} from "@/pages/data-center/syncTaskTypes";

interface SyncTaskLogDrawerProps {
  open: boolean;
  task?: SyncTaskRow;
  logs: SyncTaskLog[];
  onClose: () => void;
}

const statusColors: Record<SyncTaskStatus, string> = {
  成功: "success",
  失败: "error",
  运行中: "processing",
  部分成功: "warning",
  超时: "orange",
  已停用: "default",
};

const workStatusLabels: Record<string, SyncTaskStatus> = {
  succeeded: "成功",
  failed: "失败",
  running: "运行中",
  queued: "运行中",
  canceled: "已停用",
};

const triggerTypes: SyncTaskTriggerType[] = ["自动", "手动", "重试"];
const logStatuses: SyncTaskStatus[] = ["成功", "失败", "运行中", "部分成功", "超时", "已停用"];

function safeJson(value: Record<string, unknown>) {
  try {
    return JSON.stringify(value);
  } catch {
    return "{}";
  }
}

function statusTag(value: string) {
  const label = workStatusLabels[value] ?? "失败";
  return <Tag color={statusColors[label]}>{label}</Tag>;
}

function errorText(reason: unknown) {
  if (!reason) return undefined;
  return reason instanceof Error ? reason.message : "BACKEND_REQUEST_FAILED";
}

function SyncTaskLogDrawer({ open, task, logs, onClose }: SyncTaskLogDrawerProps) {
  const [status, setStatus] = useState<SyncTaskStatus>();
  const [triggerType, setTriggerType] = useState<SyncTaskTriggerType>();
  const [detailLog, setDetailLog] = useState<SyncTaskLog>();

  const detailRunId = detailLog?.id;
  const workItemsQuery = useIntegrationSyncRunWorkItemsQuery(detailRunId, Boolean(detailLog));
  const rawRefsQuery = useIntegrationSyncRunRawRequestRefsQuery(detailRunId, Boolean(detailLog));
  const workItems = workItemsQuery.data ?? [];
  const rawRefs = rawRefsQuery.data ?? [];
  const detailLoading = workItemsQuery.isFetching || rawRefsQuery.isFetching;
  const workItemError = errorText(workItemsQuery.error);
  const rawRefError = errorText(rawRefsQuery.error);

  const filteredLogs = useMemo(() => logs.filter((log) => (
    (!task || log.taskId === task.id)
    && (!status || log.status === status)
    && (!triggerType || log.triggerType === triggerType)
  )), [logs, status, task, triggerType]);

  const resetFilters = () => {
    setStatus(undefined);
    setTriggerType(undefined);
  };

  const openDetailLog = (log: SyncTaskLog) => {
    setDetailLog(log);
  };

  const closeDetailLog = () => {
    setDetailLog(undefined);
  };

  const logColumns: TableColumnsType<SyncTaskLog> = [
    { title: "执行时间", dataIndex: "runAt", key: "runAt", width: 150 },
    { title: "触发方式", dataIndex: "triggerType", key: "triggerType", width: 92 },
    {
      title: "执行状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (value: SyncTaskStatus) => <Tag color={statusColors[value]}>{value}</Tag>,
    },
    { title: "耗时", dataIndex: "duration", key: "duration", width: 90 },
    {
      title: "总数",
      dataIndex: "total",
      key: "total",
      width: 78,
      render: (value?: number) => value ?? "-",
    },
    {
      title: "成功/失败",
      key: "result",
      width: 100,
      render: (_, log) => log.success === undefined ? "-" : `${log.success} / ${log.failed ?? 0}`,
    },
    { title: "request_id", dataIndex: "requestId", key: "requestId", width: 110 },
    {
      title: "操作",
      key: "actions",
      width: 80,
      render: (_, log) => <Button type="link" onClick={() => openDetailLog(log)}>详情</Button>,
    },
  ];

  const workItemColumns: TableColumnsType<SyncTaskWorkItem> = [
    { title: "批次", dataIndex: "ordinal", key: "ordinal", width: 70 },
    { title: "请求类型", dataIndex: "requestKind", key: "requestKind", width: 116 },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 96,
      render: (value: string) => statusTag(value),
    },
    { title: "尝试次数", dataIndex: "attemptCount", key: "attemptCount", width: 86 },
    {
      title: "响应数量",
      dataIndex: "responseCount",
      key: "responseCount",
      width: 86,
      render: (value: number | null) => value ?? "-",
    },
    {
      title: "安全参数",
      dataIndex: "requestSafeParams",
      key: "requestSafeParams",
      width: 170,
      render: (value: Record<string, unknown>) => (
        <Typography.Text code ellipsis={{ tooltip: safeJson(value) }}>{safeJson(value)}</Typography.Text>
      ),
    },
    {
      title: "错误码",
      dataIndex: "errorCode",
      key: "errorCode",
      width: 180,
      render: (value: string | null) => value ?? "-",
    },
  ];

  const rawRefColumns: TableColumnsType<SyncTaskRawRequestRef> = [
    { title: "尝试", dataIndex: "attemptNo", key: "attemptNo", width: 64 },
    { title: "HTTP", dataIndex: "httpStatus", key: "httpStatus", width: 72, render: (value: number | null) => value ?? "-" },
    { title: "Provider Code", dataIndex: "providerCode", key: "providerCode", width: 118, render: (value: string | null) => value ?? "-" },
    {
      title: "成功",
      dataIndex: "isSuccess",
      key: "isSuccess",
      width: 70,
      render: (value: boolean) => <Tag color={value ? "success" : "error"}>{value ? "是" : "否"}</Tag>,
    },
    { title: "数量", dataIndex: "responseCount", key: "responseCount", width: 70, render: (value: number | null) => value ?? "-" },
    { title: "大小", dataIndex: "payloadBytes", key: "payloadBytes", width: 86 },
    { title: "存储", dataIndex: "storageMode", key: "storageMode", width: 90 },
    {
      title: "Hash",
      dataIndex: "responseHash",
      key: "responseHash",
      width: 160,
      render: (value: string) => <Typography.Text code ellipsis={{ tooltip: value }}>{value}</Typography.Text>,
    },
  ];

  return (
    <>
      <Drawer
        className="sync-task__log-drawer"
        title={task ? `任务执行日志：${task.taskName}` : "任务执行日志"}
        width={760}
        open={open}
        destroyOnClose
        onClose={onClose}
      >
        <Space className="sync-task__log-toolbar" wrap>
          <Select
            allowClear
            className="sync-task__log-filter"
            placeholder="全部状态"
            value={status}
            options={logStatuses.map((value) => ({ label: value, value }))}
            onChange={setStatus}
          />
          <Select
            allowClear
            className="sync-task__log-filter"
            placeholder="全部触发方式"
            value={triggerType}
            options={triggerTypes.map((value) => ({ label: value, value }))}
            onChange={setTriggerType}
          />
          <DatePicker.RangePicker className="sync-task__log-range" />
          <Button onClick={resetFilters}>重置</Button>
        </Space>
        <Table<SyncTaskLog>
          size="small"
          rowKey="id"
          columns={logColumns}
          dataSource={filteredLogs}
          pagination={{ pageSize: 8, showTotal: (total) => `共 ${total} 条` }}
          scroll={{ x: "max-content" }}
        />
        <section className="sync-task__notice-section">
          <h3>失败原因摘要</h3>
          <div className="sync-task__notice-box">
            仅展示治理表中的安全状态、计数和错误码，不展示请求或响应原文。
          </div>
        </section>
      </Drawer>
      <Modal
        title="执行明细"
        open={Boolean(detailLog)}
        width={980}
        onCancel={closeDetailLog}
        footer={<Button type="primary" onClick={closeDetailLog}>关闭</Button>}
      >
        {detailLog && (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Space direction="vertical" size={4}>
              <Typography.Text>执行时间：{detailLog.runAt}</Typography.Text>
              <Typography.Text>触发方式：{detailLog.triggerType}</Typography.Text>
              <Typography.Text>执行状态：{detailLog.status}</Typography.Text>
              <Typography.Text>request_id：{detailLog.requestId ?? "-"}</Typography.Text>
              <Typography.Text type="secondary">
                错误码：{detailLog.errorSummary ?? "-"}
              </Typography.Text>
            </Space>

            <Alert
              showIcon
              type="info"
              message="安全展示范围"
              description="这里只读取 Work Item 与 Raw Metadata，不展示原始 payload、不触发同步、不重试任务。"
            />

            {workItemError && <Alert showIcon type="warning" message="Work Item 读取失败" description={workItemError} />}
            <Table<SyncTaskWorkItem>
              size="small"
              rowKey="id"
              loading={detailLoading}
              columns={workItemColumns}
              dataSource={workItems}
              pagination={false}
              scroll={{ x: "max-content" }}
              title={() => "Work Items"}
            />

            {rawRefError && <Alert showIcon type="warning" message="Raw Metadata 读取失败" description={rawRefError} />}
            <Table<SyncTaskRawRequestRef>
              size="small"
              rowKey="id"
              loading={detailLoading}
              columns={rawRefColumns}
              dataSource={rawRefs}
              pagination={false}
              scroll={{ x: "max-content" }}
              title={() => "Raw Request Metadata"}
            />
          </Space>
        )}
      </Modal>
    </>
  );
}

export default SyncTaskLogDrawer;

import {
  Alert,
  Button,
  DatePicker,
  Descriptions,
  Empty,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
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
import { formatSyncTaskDateTime } from "@/pages/data-center/syncTaskDisplayFormatters";

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
const logStatuses: SyncTaskStatus[] = [
  "成功",
  "失败",
  "运行中",
  "部分成功",
  "超时",
  "已停用",
];

function statusTag(value: string) {
  const label = workStatusLabels[value] ?? "失败";
  return <Tag color={statusColors[label]}>{label}</Tag>;
}

function errorText(reason: unknown) {
  if (!reason) return undefined;
  return reason instanceof Error ? reason.message : "BACKEND_REQUEST_FAILED";
}

function shortId(value?: string | null) {
  if (!value) return "-";
  return value.length > 12
    ? `${value.slice(0, 8)}...${value.slice(-4)}`
    : value;
}

function formatDurationToReadable(value?: string | null) {
  if (!value) return "-";

  const msMatch = value.match(/^(\d+)ms$/);
  const secondsMatch = value.match(/^(\d+(?:\.\d+)?)s$/);

  let totalSeconds: number | null = null;

  if (msMatch) {
    const ms = Number(msMatch[1]);
    if (!Number.isFinite(ms)) return value;
    if (ms < 1000) return "<1秒";
    totalSeconds = Math.round(ms / 1000);
  } else if (secondsMatch) {
    totalSeconds = Math.round(Number(secondsMatch[1]));
  }

  if (totalSeconds === null || !Number.isFinite(totalSeconds)) {
    return value;
  }

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes <= 0) {
    return `${seconds}秒`;
  }

  return `${minutes}分${String(seconds).padStart(2, "0")}秒`;
}

function failureStage(errorCode?: string | null) {
  if (!errorCode) return "-";
  if (errorCode.includes("AUTH")) return "授权";
  if (errorCode.includes("LOCK")) return "锁";
  if (errorCode.includes("TRANSPORT") || errorCode.includes("HTTP"))
    return "请求";
  if (
    errorCode.includes("OWNER") ||
    errorCode.includes("PARSE") ||
    errorCode.includes("ANOMALY")
  )
    return "解析";
  if (errorCode.includes("MART") || errorCode.includes("WRITE"))
    return "写入/汇总";
  if (errorCode.includes("SYNC_EXECUTION")) return "执行";
  return "待确认";
}

function diagnosisByCode(errorCode?: string | null) {
  if (!errorCode) {
    return {
      title: "暂无错误码",
      description:
        "当前执行没有记录错误码。若任务仍在运行，请等待结束后再查看。",
      suggestions: [
        "等待任务完成",
        "查看 执行批次 是否仍在 running / queued",
        "确认是否存在同组 dataPages 锁",
      ],
    };
  }

  if (errorCode.includes("AUTH")) {
    return {
      title: "授权阶段失败",
      description:
        "请求未产生 执行元信息 时，通常代表失败发生在 token、授权开关或执行前置校验阶段。",
      suggestions: [
        "检查 worker 实际环境变量",
        "执行 token smoke test",
        "对比自动执行和手动/重试执行是否都失败",
        "若手动成功但自动失败，优先排查 schedule 执行路径",
      ],
    };
  }

  if (errorCode.includes("SYNC_EXECUTION")) {
    return {
      title: "同步执行阶段失败",
      description:
        "执行器抛出通用失败，当前安全日志未暴露原始响应，需要结合 执行批次、执行元信息 和事件时间线判断失败位置。",
      suggestions: [
        "查看是否生成 执行批次",
        "查看是否产生 执行元信息",
        "检查是否有 dataPages 锁",
        "若 retry 成功，优先检查自动调度并发和错峰配置",
      ],
    };
  }

  if (errorCode.includes("TRANSPORT") || errorCode.includes("HTTP")) {
    return {
      title: "请求阶段失败",
      description: "通常是网络、接口超时、HTTP 状态异常或服务端返回失败。",
      suggestions: [
        "查看 执行元信息 的 HTTP 和 Provider Code",
        "检查失败批次 attemptCount",
        "短时间后重试",
        "若重复失败，降低 page_size 或拆小批次",
      ],
    };
  }

  if (errorCode.includes("LOCK")) {
    return {
      title: "锁或并发冲突",
      description: "同组任务可能正在运行，当前任务需要等待或被阻止。",
      suggestions: [
        "查看当前锁是否 expired",
        "等待 running 任务结束",
        "不要重复点击重试",
        "将自动任务时间错峰",
      ],
    };
  }

  return {
    title: "待确认失败",
    description: "当前错误码未匹配内置诊断模板。",
    suggestions: [
      "复制诊断信息发给开发",
      "查看 执行批次 和 执行元信息",
      "检查最近一次手动/重试是否成功",
    ],
  };
}

function buildDiagnosisText(
  task: SyncTaskRow | undefined,
  log: SyncTaskLog,
  workItems: SyncTaskWorkItem[],
  rawRefs: SyncTaskRawRequestRef[],
) {
  return [
    `任务：${task?.taskName ?? "-"}`,
    `run_id：${log.id}`,
    `request_id：${log.requestId ?? "-"}`,
    `触发方式：${log.triggerType}`,
    `状态：${log.status}`,
    `错误码：${log.errorSummary ?? "-"}`,
    `执行时间：${log.runAt}`,
    `耗时：${log.duration ?? "-"}`,
    `执行批次：${log.success ?? 0}/${log.failed ?? 0}`,
    `执行元信息：${rawRefs.length}`,
    `失败阶段：${failureStage(log.errorSummary)}`,
    `Work Item 错误：${
      workItems
        .map((item) => item.errorCode)
        .filter(Boolean)
        .join(", ") || "-"
    }`,
  ].join("\n");
}

function copyText(value: string) {
  if (!navigator.clipboard) return;
  void navigator.clipboard.writeText(value);
}

function latestRunTime(log?: SyncTaskLog) {
  return log ? (formatSyncTaskDateTime(log.runAt) ?? log.runAt) : "-";
}

function SyncTaskLogDrawer({
  open,
  task,
  logs,
  onClose,
}: SyncTaskLogDrawerProps) {
  const [status, setStatus] = useState<SyncTaskStatus>();
  const [triggerType, setTriggerType] = useState<SyncTaskTriggerType>();
  const [detailLog, setDetailLog] = useState<SyncTaskLog>();

  const detailRunId = detailLog?.id;
  const workItemsQuery = useIntegrationSyncRunWorkItemsQuery(
    detailRunId,
    Boolean(detailLog),
  );
  const rawRefsQuery = useIntegrationSyncRunRawRequestRefsQuery(
    detailRunId,
    Boolean(detailLog),
  );
  const workItems = workItemsQuery.data ?? [];
  const rawRefs = rawRefsQuery.data ?? [];
  const detailLoading = workItemsQuery.isFetching || rawRefsQuery.isFetching;
  const workItemError = errorText(workItemsQuery.error);
  const rawRefError = errorText(rawRefsQuery.error);

  const taskLogs = useMemo(
    () => logs.filter((log) => !task || log.taskId === task.id),
    [logs, task],
  );

  const filteredLogs = useMemo(
    () =>
      taskLogs.filter(
        (log) =>
          (!status || log.status === status) &&
          (!triggerType || log.triggerType === triggerType),
      ),
    [status, taskLogs, triggerType],
  );

  const logStats = useMemo(() => {
    const successLogs = taskLogs.filter((log) => log.status === "成功");
    const failedLogs = taskLogs.filter((log) => log.status === "失败");
    const autoFailedLogs = taskLogs.filter(
      (log) => log.triggerType === "自动" && log.status === "失败",
    );
    const manualOrRetrySuccess = taskLogs.some(
      (log) =>
        (log.triggerType === "手动" || log.triggerType === "重试") &&
        log.status === "成功",
    );
    return {
      total: taskLogs.length,
      success: successLogs.length,
      failed: failedLogs.length,
      autoFailed: autoFailedLogs.length,
      latestSuccess: successLogs[0],
      latestFailed: failedLogs[0],
      autoFailureButManualSuccess:
        autoFailedLogs.length > 0 && manualOrRetrySuccess,
    };
  }, [taskLogs]);

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
    {
      title: "执行时间",
      dataIndex: "runAt",
      key: "runAt",
      width: 138,
      render: (value: string) => formatSyncTaskDateTime(value) ?? "-",
    },
    { title: "触发", dataIndex: "triggerType", key: "triggerType", width: 78 },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 88,
      render: (value: SyncTaskStatus) => (
        <Tag color={statusColors[value]}>{value}</Tag>
      ),
    },
    {
      title: "耗时",
      dataIndex: "duration",
      key: "duration",
      width: 88,
      render: (value: string | null) => formatDurationToReadable(value),
    },
    {
      title: "失败阶段",
      key: "stage",
      width: 92,
      render: (_, log) => failureStage(log.errorSummary),
    },
    {
      title: "错误码",
      dataIndex: "errorSummary",
      key: "errorSummary",
      width: 168,
      render: (value: string | null) =>
        value ? <Typography.Text code>{value}</Typography.Text> : "-",
    },
    {
      title: "请求ID",
      dataIndex: "requestId",
      key: "requestId",
      width: 110,
      render: (value: string | null) => (
        <Typography.Text copyable={Boolean(value)}>
          {shortId(value)}
        </Typography.Text>
      ),
    },
    {
      title: "操作",
      key: "actions",
      width: 72,
      fixed: "right",
      render: (_, log) => (
        <Button type="link" onClick={() => openDetailLog(log)}>
          详情
        </Button>
      ),
    },
  ];

  const workItemColumns: TableColumnsType<SyncTaskWorkItem> = [
    { title: "批次", dataIndex: "ordinal", key: "ordinal", width: 70 },
    {
      title: "请求类型",
      dataIndex: "requestKind",
      key: "requestKind",
      width: 116,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 96,
      render: (value: string) => statusTag(value),
    },
    {
      title: "尝试次数",
      dataIndex: "attemptCount",
      key: "attemptCount",
      width: 86,
    },
    {
      title: "响应数量",
      dataIndex: "responseCount",
      key: "responseCount",
      width: 86,
      render: (value: number | null) => value ?? "-",
    },
    {
      title: "错误码",
      dataIndex: "errorCode",
      key: "errorCode",
      width: 170,
      render: (value: string | null) => value ?? "-",
    },
    {
      title: "错误说明",
      dataIndex: "errorMessage",
      key: "errorMessage",
      width: 190,
      render: (value: string | null) => value ?? "-",
    },
  ];

  const rawRefColumns: TableColumnsType<SyncTaskRawRequestRef> = [
    { title: "尝试", dataIndex: "attemptNo", key: "attemptNo", width: 64 },
    {
      title: "状态码",
      dataIndex: "httpStatus",
      key: "httpStatus",
      width: 72,
      render: (value: number | null) => value ?? "-",
    },
    {
      title: "平台码",
      dataIndex: "providerCode",
      key: "providerCode",
      width: 118,
      render: (value: string | null) => value ?? "-",
    },
    {
      title: "成功",
      dataIndex: "isSuccess",
      key: "isSuccess",
      width: 70,
      render: (value: boolean) => (
        <Tag color={value ? "success" : "error"}>{value ? "是" : "否"}</Tag>
      ),
    },
    {
      title: "数量",
      dataIndex: "responseCount",
      key: "responseCount",
      width: 70,
      render: (value: number | null) => value ?? "-",
    },
    {
      title: "大小",
      dataIndex: "payloadBytes",
      key: "payloadBytes",
      width: 86,
    },
    { title: "存储", dataIndex: "storageMode", key: "storageMode", width: 90 },
    {
      title: "创建时间",
      dataIndex: "receivedAt",
      key: "receivedAt",
      width: 148,
      render: (value: string) => formatSyncTaskDateTime(value) ?? value,
    },
  ];

  const diagnosis = diagnosisByCode(detailLog?.errorSummary);

  const timelineItems = detailLog
    ? [
        {
          key: "queued",
          label: "任务创建",
          children: `${latestRunTime(detailLog)} · ${detailLog.triggerType}触发`,
        },
        {
          key: "status",
          label: "执行结果",
          children: `${detailLog.status} · ${detailLog.errorSummary ?? "无错误码"}`,
        },
        ...workItems.slice(0, 8).map((item) => ({
          key: item.id,
          label: `Work Item #${item.ordinal}`,
          children: `${workStatusLabels[item.status] ?? item.status} · ${item.errorCode ?? "无错误码"} · 响应 ${item.responseCount ?? "-"}`,
        })),
      ]
    : [];

  return (
    <>
      <Modal
        centered
        zIndex={1000}
        className="sync-task__log-modal sync-task__log-modal-v2"
        title={task ? `任务执行日志：${task.taskName}` : "任务执行日志"}
        width={1040}
        open={open}
        destroyOnHidden
        onCancel={onClose}
        footer={
          <Button type="primary" onClick={onClose}>
            关闭
          </Button>
        }
      >
        <div className="sync-task__log-summary-grid">
          <div className="sync-task__log-summary-card">
            <span>今日执行</span>
            <strong>{logStats.total}</strong>
          </div>
          <div className="sync-task__log-summary-card">
            <span>成功</span>
            <strong>{logStats.success}</strong>
          </div>
          <div className="sync-task__log-summary-card sync-task__log-summary-card--danger">
            <span>失败</span>
            <strong>{logStats.failed}</strong>
          </div>
          <div className="sync-task__log-summary-card">
            <span>最近成功</span>
            <strong>{latestRunTime(logStats.latestSuccess)}</strong>
          </div>
        </div>

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
          <Button onClick={() => setStatus("失败")}>只看异常</Button>
          <Button onClick={resetFilters}>重置</Button>
        </Space>

        <Table<SyncTaskLog>
          size="small"
          rowKey="id"
          columns={logColumns}
          dataSource={filteredLogs}
          pagination={{ pageSize: 8, showTotal: (total) => `共 ${total} 条` }}
          scroll={{ x: "max-content", y: 420 }}
        />
      </Modal>

      <Modal
        centered
        zIndex={1600}
        className="sync-task__run-detail-modal"
        title={
          detailLog
            ? `${detailLog.status} · ${task?.taskName ?? "执行详情"} · ${detailLog.errorSummary ?? "无错误码"}`
            : "执行详情"
        }
        open={Boolean(detailLog)}
        width={1080}
        onCancel={closeDetailLog}
        footer={
          <Space>
            {detailLog && (
              <Button
                onClick={() =>
                  copyText(
                    buildDiagnosisText(task, detailLog, workItems, rawRefs),
                  )
                }
              >
                复制诊断信息
              </Button>
            )}
            <Button type="primary" onClick={closeDetailLog}>
              关闭
            </Button>
          </Space>
        }
      >
        {detailLog && (
          <Tabs
            items={[
              {
                key: "overview",
                label: "概览",
                children: (
                  <Space
                    direction="vertical"
                    size={14}
                    style={{ width: "100%" }}
                  >
                    <Alert
                      showIcon
                      type={
                        detailLog.status === "成功"
                          ? "success"
                          : detailLog.status === "运行中"
                            ? "info"
                            : "error"
                      }
                      message={`${detailLog.status} · ${failureStage(detailLog.errorSummary)}`}
                      description={diagnosis.description}
                    />
                    <Descriptions
                      bordered
                      size="small"
                      column={2}
                      items={[
                        {
                          key: "run_id",
                          label: "run_id",
                          children: (
                            <Typography.Text copyable>
                              {shortId(detailLog.id)}
                            </Typography.Text>
                          ),
                        },
                        {
                          key: "request_id",
                          label: "request_id",
                          children: (
                            <Typography.Text
                              copyable={Boolean(detailLog.requestId)}
                            >
                              {shortId(detailLog.requestId)}
                            </Typography.Text>
                          ),
                        },
                        {
                          key: "trigger",
                          label: "触发方式",
                          children: detailLog.triggerType,
                        },
                        {
                          key: "status",
                          label: "执行状态",
                          children: (
                            <Tag color={statusColors[detailLog.status]}>
                              {detailLog.status}
                            </Tag>
                          ),
                        },
                        {
                          key: "time",
                          label: "执行时间",
                          children:
                            formatSyncTaskDateTime(detailLog.runAt) ??
                            detailLog.runAt,
                        },
                        {
                          key: "duration",
                          label: "耗时",
                          children: detailLog.duration ?? "-",
                        },
                        {
                          key: "items",
                          label: "执行批次",
                          children: `${detailLog.success ?? 0} / ${detailLog.failed ?? 0}`,
                        },
                        {
                          key: "raw",
                          label: "执行元信息",
                          children: rawRefs.length,
                        },
                        {
                          key: "records",
                          label: "数据量",
                          children: `seen ${detailLog.total ?? 0}`,
                        },
                        {
                          key: "error",
                          label: "错误码",
                          children: detailLog.errorSummary ?? "-",
                        },
                      ]}
                    />
                  </Space>
                ),
              },
              {
                key: "work-items",
                label: "执行批次",
                children: (
                  <Space
                    direction="vertical"
                    size={12}
                    style={{ width: "100%" }}
                  >
                    {workItemError && (
                      <Alert
                        showIcon
                        type="warning"
                        message="Work Item 读取失败"
                        description={workItemError}
                      />
                    )}
                    <Table<SyncTaskWorkItem>
                      size="small"
                      rowKey="id"
                      loading={detailLoading}
                      columns={workItemColumns}
                      dataSource={workItems}
                      pagination={{
                        pageSize: 8,
                        showSizeChanger: false,
                        showTotal: (total) => `共 ${total} 条`,
                      }}
                      scroll={{ x: "max-content", y: 360 }}
                    />
                  </Space>
                ),
              },
              {
                key: "raw",
                label: "执行元信息",
                children: (
                  <Space
                    direction="vertical"
                    size={12}
                    style={{ width: "100%" }}
                  >
                    {rawRefError && (
                      <Alert
                        showIcon
                        type="warning"
                        message="执行元信息读取失败"
                        description={rawRefError}
                      />
                    )}
                    {rawRefs.length === 0 ? (
                      <Empty
                        description={
                          <span>
                            本次没有产生 Raw
                            Metadata。可能原因：请求未发出、授权阶段失败、真实请求开关未开启，或任务在前置校验阶段失败。
                          </span>
                        }
                      />
                    ) : (
                      <Table<SyncTaskRawRequestRef>
                        size="small"
                        rowKey="id"
                        loading={detailLoading}
                        columns={rawRefColumns}
                        dataSource={rawRefs}
                        pagination={{
                          pageSize: 8,
                          showSizeChanger: false,
                          showTotal: (total) => `共 ${total} 条`,
                        }}
                        scroll={{ x: "max-content", y: 360 }}
                      />
                    )}
                  </Space>
                ),
              },
              {
                key: "timeline",
                label: "事件时间线",
                children: (
                  <div className="sync-task__timeline-list">
                    {timelineItems.map((item) => (
                      <div className="sync-task__timeline-item" key={item.key}>
                        <div className="sync-task__timeline-dot" />
                        <div>
                          <strong>{item.label}</strong>
                          <p>{item.children}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ),
              },
              {
                key: "advice",
                label: "诊断建议",
                children: (
                  <Alert
                    showIcon
                    type="info"
                    message={diagnosis.title}
                    description={
                      <ul className="sync-task__advice-list">
                        {diagnosis.suggestions.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    }
                  />
                ),
              },
            ]}
          />
        )}
      </Modal>
    </>
  );
}

export default SyncTaskLogDrawer;

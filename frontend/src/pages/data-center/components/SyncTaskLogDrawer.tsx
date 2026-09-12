import { Button, DatePicker, Drawer, Modal, Select, Space, Table, Tag, Typography, type TableColumnsType } from "antd";
import { useMemo, useState } from "react";
import type {
  SyncTaskLog,
  SyncTaskRow,
  SyncTaskStatus,
  SyncTaskTriggerType,
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

const triggerTypes: SyncTaskTriggerType[] = ["自动", "手动", "重试"];
const logStatuses: SyncTaskStatus[] = ["成功", "失败", "运行中", "部分成功", "超时", "已停用"];

function SyncTaskLogDrawer({ open, task, logs, onClose }: SyncTaskLogDrawerProps) {
  const [status, setStatus] = useState<SyncTaskStatus>();
  const [triggerType, setTriggerType] = useState<SyncTaskTriggerType>();
  const [detailLog, setDetailLog] = useState<SyncTaskLog>();

  const filteredLogs = useMemo(() => logs.filter((log) => (
    (!task || log.taskId === task.id)
    && (!status || log.status === status)
    && (!triggerType || log.triggerType === triggerType)
  )), [logs, status, task, triggerType]);

  const resetFilters = () => {
    setStatus(undefined);
    setTriggerType(undefined);
  };

  const columns: TableColumnsType<SyncTaskLog> = [
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
      render: (_, log) => <Button type="link" onClick={() => setDetailLog(log)}>详情</Button>,
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
          columns={columns}
          dataSource={filteredLogs}
          pagination={{ pageSize: 8, showTotal: (total) => `共 ${total} 条` }}
          scroll={{ x: "max-content" }}
        />
        <section className="sync-task__notice-section">
          <h3>失败原因摘要</h3>
          <div className="sync-task__notice-box">
            API 请求超时；部分订单返回字段缺失。敏感参数已脱敏，完整错误请在后端日志中按 request_id 检索。
          </div>
        </section>
      </Drawer>
      <Modal
        title="执行明细"
        open={Boolean(detailLog)}
        onCancel={() => setDetailLog(undefined)}
        footer={<Button type="primary" onClick={() => setDetailLog(undefined)}>关闭</Button>}
      >
        {detailLog && (
          <Space direction="vertical" size={8}>
            <Typography.Text>执行时间：{detailLog.runAt}</Typography.Text>
            <Typography.Text>触发方式：{detailLog.triggerType}</Typography.Text>
            <Typography.Text>执行状态：{detailLog.status}</Typography.Text>
            <Typography.Text>request_id：{detailLog.requestId}</Typography.Text>
            <Typography.Text type="secondary">
              {detailLog.errorSummary ?? "本次执行未发现异常，执行明细接口待接入。"}
            </Typography.Text>
          </Space>
        )}
      </Modal>
    </>
  );
}

export default SyncTaskLogDrawer;

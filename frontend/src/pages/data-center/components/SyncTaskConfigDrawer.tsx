import {
  Button,
  Drawer,
  Form,
  Input,
  Radio,
  Select,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { useEffect } from "react";
import { normalizeSyncTaskBackfillDays } from "@/pages/data-center/syncTaskDisplayFormatters";
import type {
  SyncTaskCycle,
  SyncTaskModule,
  SyncTaskRow,
} from "@/pages/data-center/syncTaskTypes";

interface SyncTaskConfigDrawerProps {
  open: boolean;
  task?: SyncTaskRow;
  modules: SyncTaskModule[];
  onClose: () => void;
  onSave: (task: SyncTaskRow, values: SyncTaskConfigFormValues) => void;
}

export type SyncTaskFrequencyPreset =
  | "5m"
  | "10m"
  | "15m"
  | "30m"
  | "1h"
  | "2h"
  | "hourly_minutes"
  | "daily_fixed"
  | "advanced_cron";

export interface SyncTaskConfigFormValues {
  taskName: string;
  module: SyncTaskModule;
  interfaceName: string;
  description: string;
  cycle: SyncTaskCycle;
  autoSync: boolean;
  frequencyPreset: SyncTaskFrequencyPreset;
  fixedRunTimes?: string[];
  hourlyMinutes?: number[];
  customCron?: string;
  backfillDays?: number;
  dailyRunCount?: number;
  runTimes: string[];
  weekDays: string[];
  timeoutSeconds?: number;
  maxFailureTimes?: number;
  duplicatePolicy?: string;
  retryEnabled: boolean;
  retryTimes?: number;
  retryInterval?: string;
  notificationScenes: string[];
  notificationChannels: string[];
  notificationTargets?: string;
}

const notificationSceneOptions = ["失败", "部分成功", "超时", "恢复成功"];
const notificationChannelOptions = ["站内信", "飞书", "邮件"];

const frequencyOptions = [
  { label: "每 5 分钟", value: "5m" },
  { label: "每 10 分钟", value: "10m" },
  { label: "每 15 分钟", value: "15m" },
  { label: "每 30 分钟", value: "30m" },
  { label: "每 1 小时", value: "1h" },
  { label: "每 2 小时", value: "2h" },
  { label: "每小时指定分钟", value: "hourly_minutes" },
  { label: "每天固定时间", value: "daily_fixed" },
  { label: "高级 Cron", value: "advanced_cron" },
];

const dateRangeTaskKeys = new Set([
  "saleStatPageList",
  "walmartReturnOrderList",
  "walmartAdItemSpList",
]);

const dataPagesKeys = new Set([
  "walmartListingList",
  "saleStatPageList",
  "walmartReturnOrderList",
  "walmartAdItemSpList",
]);

const minuteOptions = Array.from({ length: 12 }, (_, index) => index * 5).map(
  (value) => ({
    label: `第 ${String(value).padStart(2, "0")} 分钟`,
    value,
  }),
);

const quarterHourOptions = Array.from({ length: 24 * 4 }, (_, index) => {
  const hour = Math.floor(index / 4);
  const minute = (index % 4) * 15;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}).map((value) => ({ label: value, value }));

const toChinaHour = (schedulerHour: number) => (schedulerHour + 8) % 24;

const formatTime = (hour: number, minute: number) =>
  `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;

const defaultBackfillDaysForTask = (task: SyncTaskRow) => {
  if (task.interfaceKey === "walmartReturnOrderList") return 7;
  if (task.interfaceKey === "saleStatPageList") return 3;
  if (task.interfaceKey === "walmartAdItemSpList") return 3;
  return undefined;
};

const defaultHourlyMinutesForTask = (task: SyncTaskRow) => {
  if (task.interfaceKey === "productList") return [5, 35];
  if (task.interfaceKey === "saleStatPageList") return [15, 45];
  if (task.interfaceKey === "walmartListingList") return [25];
  if (task.interfaceKey === "walmartReturnOrderList") return [40];
  if (task.interfaceKey === "walmartAdItemSpList") return [55];
  return [0];
};

const defaultFrequencyForTask = (
  task: SyncTaskRow,
): SyncTaskFrequencyPreset => {
  if (task.interfaceKey === "productList") return "hourly_minutes";
  if (task.interfaceKey === "walmartListingList") return "hourly_minutes";
  if (task.interfaceKey === "saleStatPageList") return "hourly_minutes";
  if (task.interfaceKey === "walmartReturnOrderList") return "hourly_minutes";
  if (task.interfaceKey === "walmartAdItemSpList") return "hourly_minutes";
  return "1h";
};

const defaultFixedRunTimesForTask = (task: SyncTaskRow) => {
  if (task.interfaceKey === "productList") return ["03:00"];
  return task.runTimes?.length ? task.runTimes : ["03:00"];
};

const parseCronToFormValues = (task: SyncTaskRow) => {
  const cron = task.scheduleCron?.trim();

  if (!cron) {
    return {
      frequencyPreset: defaultFrequencyForTask(task),
      hourlyMinutes: defaultHourlyMinutesForTask(task),
      fixedRunTimes: defaultFixedRunTimesForTask(task),
      customCron: "",
    };
  }

  if (cron === "*/5 * * * *") {
    return {
      frequencyPreset: "5m" as const,
      hourlyMinutes: defaultHourlyMinutesForTask(task),
      fixedRunTimes: defaultFixedRunTimesForTask(task),
      customCron: "",
    };
  }

  if (cron === "*/10 * * * *") {
    return {
      frequencyPreset: "10m" as const,
      hourlyMinutes: defaultHourlyMinutesForTask(task),
      fixedRunTimes: defaultFixedRunTimesForTask(task),
      customCron: "",
    };
  }

  if (cron === "*/15 * * * *") {
    return {
      frequencyPreset: "15m" as const,
      hourlyMinutes: defaultHourlyMinutesForTask(task),
      fixedRunTimes: defaultFixedRunTimesForTask(task),
      customCron: "",
    };
  }

  if (cron === "*/30 * * * *") {
    return {
      frequencyPreset: "30m" as const,
      hourlyMinutes: defaultHourlyMinutesForTask(task),
      fixedRunTimes: defaultFixedRunTimesForTask(task),
      customCron: "",
    };
  }

  if (cron === "0 * * * *") {
    return {
      frequencyPreset: "1h" as const,
      hourlyMinutes: [0],
      fixedRunTimes: defaultFixedRunTimesForTask(task),
      customCron: "",
    };
  }

  if (cron === "0 */2 * * *") {
    return {
      frequencyPreset: "2h" as const,
      hourlyMinutes: [0],
      fixedRunTimes: defaultFixedRunTimesForTask(task),
      customCron: "",
    };
  }

  const hourlyMinuteMatch = cron.match(/^([0-9]+(?:,[0-9]+)*) \* \* \* \*$/);
  if (hourlyMinuteMatch) {
    return {
      frequencyPreset: "hourly_minutes" as const,
      hourlyMinutes: hourlyMinuteMatch[1]
        .split(",")
        .map(Number)
        .filter(
          (value) => Number.isInteger(value) && value >= 0 && value <= 59,
        ),
      fixedRunTimes: defaultFixedRunTimesForTask(task),
      customCron: "",
    };
  }

  const dailyMatch = cron.match(/^([0-9]+) ([0-9]+(?:,[0-9]+)*) \* \* \*$/);
  if (dailyMatch) {
    const minute = Number(dailyMatch[1]);
    const fixedRunTimes = dailyMatch[2]
      .split(",")
      .map(Number)
      .filter((value) => Number.isInteger(value) && value >= 0 && value <= 23)
      .map((hour) => formatTime(toChinaHour(hour), minute));
    return {
      frequencyPreset: "daily_fixed" as const,
      hourlyMinutes: defaultHourlyMinutesForTask(task),
      fixedRunTimes: fixedRunTimes.length
        ? fixedRunTimes
        : defaultFixedRunTimesForTask(task),
      customCron: "",
    };
  }

  return {
    frequencyPreset: "advanced_cron" as const,
    hourlyMinutes: defaultHourlyMinutesForTask(task),
    fixedRunTimes: defaultFixedRunTimesForTask(task),
    customCron: cron,
  };
};

const lockGroupText = (task?: SyncTaskRow) => {
  if (!task) return "未选择任务";
  if (dataPagesKeys.has(task.interfaceKey))
    return "dataPages，同组串行，建议错峰";
  if (task.interfaceKey === "productList")
    return "productManagement，产品列表与产品详情合并展示";
  return "独立任务组";
};

function SyncTaskConfigDrawer({
  open,
  task,
  onClose,
  onSave,
}: SyncTaskConfigDrawerProps) {
  const [form] = Form.useForm<SyncTaskConfigFormValues>();
  const autoSync = Form.useWatch("autoSync", form);
  const watchedFrequencyPreset = Form.useWatch("frequencyPreset", form);
  const frequencyPreset =
    watchedFrequencyPreset ??
    (task ? defaultFrequencyForTask(task) : undefined);
  const showBackfillDays = Boolean(
    task && dateRangeTaskKeys.has(task.interfaceKey),
  );
  const showHourlyMinutes = frequencyPreset === "hourly_minutes";
  const showFixedRunTime = frequencyPreset === "daily_fixed";
  const showAdvancedCron = frequencyPreset === "advanced_cron";
  const showFrequency = Boolean(task);

  useEffect(() => {
    if (!open || !task) return;

    const scheduleValues = parseCronToFormValues(task);
    const backfillDays = normalizeSyncTaskBackfillDays(
      task.backfillDays,
      defaultBackfillDaysForTask(task),
    );

    form.setFieldsValue({
      taskName: task.taskName,
      module: task.module,
      interfaceName: task.interfaceName,
      description: task.description,
      cycle: task.autoSync ? "日任务" : "手动任务",
      autoSync: task.autoSync,
      frequencyPreset: scheduleValues.frequencyPreset,
      fixedRunTimes: scheduleValues.fixedRunTimes,
      hourlyMinutes: scheduleValues.hourlyMinutes,
      customCron: scheduleValues.customCron,
      backfillDays,
      dailyRunCount: undefined,
      runTimes: scheduleValues.fixedRunTimes,
      weekDays: task.weekDays,
      timeoutSeconds: undefined,
      maxFailureTimes: undefined,
      duplicatePolicy: undefined,
      retryEnabled: true,
      retryTimes: 2,
      retryInterval: "15 分钟、30 分钟",
      notificationScenes: task.notificationScenes,
      notificationChannels: task.notificationChannels,
      notificationTargets: task.notificationTargets ?? undefined,
    });
  }, [form, open, task]);

  return (
    <Drawer
      className="sync-task__config-drawer sync-task__config-drawer-v2"
      title="配置同步任务"
      width={760}
      open={open}
      destroyOnHidden
      onClose={onClose}
      extra={
        <Typography.Text type="secondary">
          {task ? task.taskName : "未选择任务"}
        </Typography.Text>
      }
    >
      <Form
        form={form}
        layout="vertical"
        className="sync-task__config-form sync-task__config-form-v2"
      >
        <section className="sync-task__drawer-section">
          <h3>任务介绍</h3>
          <div className="sync-task__intro-card">
            <div className="sync-task__intro-main">
              <div className="sync-task__intro-title-row">
                <strong>{task?.taskName ?? "未选择任务"}</strong>
                <Tag
                  color={
                    task && dataPagesKeys.has(task.interfaceKey)
                      ? "blue"
                      : "green"
                  }
                >
                  {task?.module ?? "-"}
                </Tag>
              </div>
              <Typography.Text type="secondary">
                {task?.description ??
                  "基础信息来自接口目录，仅作展示；本页只保存执行计划。"}
              </Typography.Text>
            </div>
          </div>

          <div className="sync-task__intro-grid">
            <div className="sync-task__intro-item">
              <span>包含接口</span>
              <strong>{task?.interfaceName ?? "-"}</strong>
            </div>
            <div className="sync-task__intro-item">
              <span>接口 Key</span>
              <strong>{task?.interfaceKey ?? "-"}</strong>
            </div>
            <div className="sync-task__intro-item">
              <span>同步组 / 并发策略</span>
              <strong>{lockGroupText(task)}</strong>
            </div>
            <div className="sync-task__intro-item">
              <span>数据源账号</span>
              <strong>{task?.source ?? "primary"}</strong>
            </div>
          </div>
        </section>

        <section className="sync-task__drawer-section">
          <h3>执行计划</h3>
          <div className="sync-task__form-grid">
            <Form.Item
              name="autoSync"
              label="运行方式"
              rules={[{ required: true, message: "请选择运行方式" }]}
            >
              <Radio.Group
                options={[
                  { label: "自动任务", value: true },
                  { label: "手动任务", value: false },
                ]}
                onChange={(event) => {
                  form.setFieldValue(
                    "cycle",
                    event.target.value ? "日任务" : "手动任务",
                  );
                }}
              />
            </Form.Item>

            <Form.Item name="cycle" hidden>
              <Input />
            </Form.Item>

            {autoSync && showFrequency && (
              <Form.Item
                name="frequencyPreset"
                label="调度模式"
                className="sync-task__schedule-mode-field"
                rules={[{ required: true, message: "请选择调度模式" }]}
              >
                <Select
                  className="sync-task__schedule-mode-select"
                  options={frequencyOptions}
                  placeholder="选择自动同步的执行方式"
                />
              </Form.Item>
            )}

            {autoSync && showHourlyMinutes && (
              <Form.Item
                name="hourlyMinutes"
                label="每小时第几分钟执行"
                rules={[
                  {
                    required: true,
                    type: "array",
                    min: 1,
                    message: "请选择至少一个分钟点",
                  },
                ]}
              >
                <Select
                  mode="multiple"
                  maxTagCount="responsive"
                  options={minuteOptions}
                  placeholder="例如 15、45，表示每小时第 15 和 45 分钟执行"
                />
              </Form.Item>
            )}

            {autoSync && showFixedRunTime && (
              <Form.Item
                name="fixedRunTimes"
                label="每天固定时间"
                rules={[
                  {
                    required: true,
                    type: "array",
                    min: 1,
                    message: "请选择至少一个执行时间",
                  },
                ]}
              >
                <Select
                  mode="multiple"
                  showSearch
                  maxTagCount="responsive"
                  options={quarterHourOptions}
                  placeholder="可多选，例如 08:15、12:15、18:15"
                />
              </Form.Item>
            )}

            {autoSync && showAdvancedCron && (
              <Form.Item
                name="customCron"
                label="高级 Cron"
                rules={[{ required: true, message: "请输入 Cron 表达式" }]}
              >
                <Input placeholder="例如：15,45 * * * *" />
              </Form.Item>
            )}

            {autoSync && showBackfillDays && (
              <Form.Item
                name="backfillDays"
                label="业务日期回刷范围"
                className="sync-task__backfill-field"
                rules={[{ required: true, message: "请选择每次回刷范围" }]}
              >
                <Select
                  className="sync-task__backfill-select"
                  options={[
                    { label: "仅今天", value: 1 },
                    { label: "最近 2 天", value: 2 },
                    { label: "最近 3 天", value: 3 },
                    { label: "最近 5 天", value: 5 },
                    { label: "最近 7 天", value: 7 },
                    { label: "最近 10 天", value: 10 },
                    { label: "最近 14 天", value: 14 },
                    { label: "最近 30 天", value: 30 },
                  ]}
                  placeholder="选择每次自动同步要回刷的业务日期范围"
                />
              </Form.Item>
            )}
          </div>
        </section>

        <section className="sync-task__drawer-section">
          <h3>通知设置</h3>
          <Typography.Paragraph type="secondary">
            通知持久化接口尚未接入，当前只展示任务现状，不参与本次保存。
          </Typography.Paragraph>
          <Form.Item name="notificationScenes" label="通知场景">
            <Select
              disabled
              mode="multiple"
              options={notificationSceneOptions.map((value) => ({
                label: value,
                value,
              }))}
            />
          </Form.Item>
          <Form.Item name="notificationChannels" label="通知方式">
            <Select
              disabled
              mode="multiple"
              options={notificationChannelOptions.map((value) => ({
                label: value,
                value,
              }))}
            />
          </Form.Item>
          <Form.Item name="notificationTargets" label="通知对象">
            <Input disabled />
          </Form.Item>
        </section>

        <div className="sync-task__drawer-actions">
          <Button onClick={onClose}>取消</Button>
          <Tooltip title="保存前会进行二次确认">
            <Button
              type="primary"
              onClick={() => task && onSave(task, form.getFieldsValue())}
            >
              保存配置
            </Button>
          </Tooltip>
        </div>
      </Form>
    </Drawer>
  );
}

export default SyncTaskConfigDrawer;

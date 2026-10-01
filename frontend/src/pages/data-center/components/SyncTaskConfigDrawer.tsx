import { Alert, Button, Drawer, Form, Input, Radio, Select, Tooltip, Typography } from "antd";
import { useEffect } from "react";
import {
  normalizeSyncTaskBackfillDays,
  parseSyncTaskSchedule,
} from "@/pages/data-center/syncTaskDisplayFormatters";
import type { SyncTaskCycle, SyncTaskModule, SyncTaskRow } from "@/pages/data-center/syncTaskTypes";

interface SyncTaskConfigDrawerProps {
  open: boolean;
  task?: SyncTaskRow;
  modules: SyncTaskModule[];
  onClose: () => void;
  onSave: (task: SyncTaskRow, values: SyncTaskConfigFormValues) => void;
}

export type SyncTaskFrequencyPreset = "30m" | "1h" | "2h" | "daily_fixed";

export interface SyncTaskConfigFormValues {
  taskName: string;
  module: SyncTaskModule;
  interfaceName: string;
  description: string;
  cycle: SyncTaskCycle;
  autoSync: boolean;
  frequencyPreset: SyncTaskFrequencyPreset;
  fixedRunTimes?: string[];
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
  { label: "每 30 分钟", value: "30m" },
  { label: "每 1 小时", value: "1h" },
  { label: "每 2 小时", value: "2h" },
  { label: "每天固定时间", value: "daily_fixed" },
];

const dateRangeTaskKeys = new Set([
  "saleStatPageList",
  "walmartReturnOrderList",
  "walmartAdItemSpList",
]);



const defaultFrequencyForTask = (task: SyncTaskRow): SyncTaskFrequencyPreset => {
  if (task.interfaceKey === "productList") return "daily_fixed";
  if (task.interfaceKey === "walmartListingList") return "30m";
  if (task.interfaceKey === "saleStatPageList") return "30m";
  if (task.interfaceKey === "walmartReturnOrderList") return "1h";
  if (task.interfaceKey === "walmartAdItemSpList") return "1h";
  return "1h";
};

const defaultFixedTimeForTask = (task: SyncTaskRow) => {
  if (task.interfaceKey === "productList") return "03:00";
  return task.runTimes?.[0] ?? "03:00";
};

const defaultBackfillDaysForTask = (task: SyncTaskRow) => {
  if (task.interfaceKey === "walmartReturnOrderList") return 7;
  if (task.interfaceKey === "saleStatPageList") return 3;
  if (task.interfaceKey === "walmartAdItemSpList") return 3;
  return undefined;
};

const taskPolicyText = (task?: SyncTaskRow) => {
  if (!task) return "系统按任务类型自动设置超时、重试和重复触发策略。";

  if (task.interfaceKey === "productList") {
    return "产品管理同步默认每天固定时间执行；失败自动重试 2 次；运行中再次触发会跳过本次。";
  }

  if (task.interfaceKey === "walmartListingList") {
    return "Listing 管理同步默认全天 24 小时执行；失败自动重试 2 次；其他同步运行中时新任务排队等待。";
  }

  if (task.interfaceKey === "saleStatPageList") {
    return "每日销售同步按美国洛杉矶业务日期回刷；失败自动重试 2 次；其他同步运行中时新任务排队等待。";
  }

  if (task.interfaceKey === "walmartReturnOrderList") {
    return "退款退货同步按美国洛杉矶业务日期回刷；失败自动重试 2 次；其他同步运行中时新任务排队等待。";
  }

  if (task.interfaceKey === "walmartAdItemSpList") {
    return "广告报表同步按美国洛杉矶业务日期回刷；失败自动重试 2 次；其他同步运行中时新任务排队等待。";
  }

  return "系统按任务类型自动设置超时、重试和重复触发策略。";
};

function SyncTaskConfigDrawer({
  open,
  task,
  modules,
  onClose,
  onSave,
}: SyncTaskConfigDrawerProps) {
  const [form] = Form.useForm<SyncTaskConfigFormValues>();
  const autoSync = Form.useWatch("autoSync", form);
  const watchedFrequencyPreset = Form.useWatch("frequencyPreset", form);
  const frequencyPreset = watchedFrequencyPreset ?? (task ? defaultFrequencyForTask(task) : undefined);
  const showBackfillDays = Boolean(task && dateRangeTaskKeys.has(task.interfaceKey));
  const showFixedRunTime = frequencyPreset === "daily_fixed";
  const showFrequency = Boolean(task);
  const showNoDateRangeNotice = Boolean(task && !dateRangeTaskKeys.has(task.interfaceKey));

  useEffect(() => {
    if (!open || !task) return;

    const savedSchedule = parseSyncTaskSchedule(task.scheduleCron);
    const frequency = savedSchedule?.preset ?? defaultFrequencyForTask(task);
    const fixedRunTimes = savedSchedule?.fixedRunTimes.length
      ? savedSchedule.fixedRunTimes
      : [defaultFixedTimeForTask(task)];
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
      frequencyPreset: frequency,
      fixedRunTimes,
      backfillDays,
      dailyRunCount: undefined,
      runTimes: fixedRunTimes,
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
      className="sync-task__config-drawer"
      title="配置同步任务"
      width={680}
      open={open}
      destroyOnHidden
      onClose={onClose}
      extra={(
        <Typography.Text type="secondary">
          {task ? task.taskName : "未选择任务"}
        </Typography.Text>
      )}
    >
      <Alert
        showIcon
        type="info"
        message="只配置业务需要的内容"
        description="系统会全天 24 小时按频率自动执行；执行超时、失败重试、重复触发策略由底层默认控制。"
        style={{ marginBottom: 16 }}
      />

      <Form
        form={form}
        layout="vertical"
        className="sync-task__config-form"
      >
        <section className="sync-task__drawer-section">
          <h3>基础信息</h3>
          <Typography.Paragraph type="secondary">
            基础信息来自接口目录，仅作展示；本页保存执行计划，不会修改任务名称、模块、接口或说明。
          </Typography.Paragraph>
          <div className="sync-task__form-grid">
            <Form.Item name="taskName" label="任务名称">
              <Input disabled />
            </Form.Item>
            <Form.Item name="module" label="所属模块">
              <Select disabled options={modules.map((module) => ({ label: module, value: module }))} />
            </Form.Item>
            <Form.Item name="interfaceName" label="包含接口">
              <Input disabled />
            </Form.Item>
            <Form.Item name="description" label="任务说明" className="sync-task__form-grid-full">
              <Input.TextArea disabled rows={3} />
            </Form.Item>
          </div>
        </section>

        <section className="sync-task__drawer-section">
          <h3>执行计划</h3>
          <div className="sync-task__form-grid">
            <Form.Item name="autoSync" label="运行方式" rules={[{ required: true, message: "请选择运行方式" }]}>
              <Radio.Group
                options={[
                  { label: "自动任务", value: true },
                  { label: "手动任务", value: false },
                ]}
                onChange={(event) => {
                  form.setFieldValue("cycle", event.target.value ? "日任务" : "手动任务");
                }}
              />
            </Form.Item>

            <Form.Item name="cycle" hidden>
              <Input />
            </Form.Item>

            {autoSync && showFrequency && (
              <Form.Item name="frequencyPreset" label="执行频率" rules={[{ required: true, message: "请选择执行频率" }]}>
                <Radio.Group options={frequencyOptions} />
              </Form.Item>
            )}

            {autoSync && showFixedRunTime && (
              <Form.Item
                name="fixedRunTimes"
                label="每天几点执行"
                rules={[{ required: true, type: "array", min: 1, message: "请选择至少一个执行时间" }]}
              >
                <Select
                  mode="multiple"
                  maxTagCount="responsive"
                  options={[
                    "00:00",
                    "01:00",
                    "02:00",
                    "03:00",
                    "04:00",
                    "05:00",
                    "06:00",
                    "08:00",
                    "10:00",
                    "12:00",
                    "14:00",
                    "16:00",
                    "18:00",
                    "20:00",
                    "22:00",
                  ].map((value) => ({ label: value, value }))}
                  placeholder="可多选，例如 03:00、08:00、14:00"
                />
              </Form.Item>
            )}

            {autoSync && showBackfillDays && (
              <Form.Item
                name="backfillDays"
                label="每次回刷范围"
                rules={[{ required: true, message: "请选择每次回刷范围" }]}
              >
                <Radio.Group
                  options={[
                    { label: "仅今天", value: 1 },
                    { label: "最近 2 天", value: 2 },
                    { label: "最近 3 天", value: 3 },
                    { label: "最近 7 天", value: 7 },
                    { label: "最近 14 天", value: 14 },
                  ]}
                />
              </Form.Item>
            )}

            {autoSync && showNoDateRangeNotice && (
              <Form.Item label="回刷说明" className="sync-task__form-grid-full">
                <Typography.Text type="secondary">
                  当前任务同步当前状态，不需要选择回刷天数。
                </Typography.Text>
              </Form.Item>
            )}

            {autoSync && (
              <Form.Item label="执行说明" className="sync-task__form-grid-full">
                <Typography.Text type="secondary">
                  系统全天 24 小时自动执行；业务日期按美国洛杉矶时间计算。
                </Typography.Text>
              </Form.Item>
            )}
          </div>
        </section>

        <section className="sync-task__drawer-section">
          <h3>系统默认策略</h3>
          <Alert
            type="success"
            showIcon
            message="底层自动处理"
            description={taskPolicyText(task)}
          />
          <div style={{ marginTop: 12 }}>
            <Typography.Text type="secondary">
              默认策略：失败自动重试 2 次；重试间隔 15 分钟、30 分钟；重复触发策略由任务类型控制，不取消健康运行中的任务；执行超时按任务类型自动设置。
            </Typography.Text>
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
              options={notificationSceneOptions.map((value) => ({ label: value, value }))}
            />
          </Form.Item>
          <Form.Item name="notificationChannels" label="通知方式">
            <Select
              disabled
              mode="multiple"
              options={notificationChannelOptions.map((value) => ({ label: value, value }))}
            />
          </Form.Item>
          <Form.Item name="notificationTargets" label="通知对象">
            <Input disabled />
          </Form.Item>
        </section>

        <div className="sync-task__drawer-actions">
          <Button onClick={onClose}>取消</Button>
          <Tooltip title="保存前会进行二次确认">
            <Button type="primary" onClick={() => task && onSave(task, form.getFieldsValue())}>
              保存配置
            </Button>
          </Tooltip>
        </div>
      </Form>
    </Drawer>
  );
}

export default SyncTaskConfigDrawer;

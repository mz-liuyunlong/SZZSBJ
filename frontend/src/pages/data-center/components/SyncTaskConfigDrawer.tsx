import { Button, Drawer, Form, Input, InputNumber, Radio, Select, Switch, Typography } from "antd";
import { useEffect } from "react";
import type { SyncTaskCycle, SyncTaskModule, SyncTaskRow } from "@/pages/data-center/syncTaskTypes";

interface SyncTaskConfigDrawerProps {
  open: boolean;
  task?: SyncTaskRow;
  modules: SyncTaskModule[];
  onClose: () => void;
  onSave: (task: SyncTaskRow) => void;
}

interface SyncTaskConfigFormValues {
  taskName: string;
  module: SyncTaskModule;
  interfaceName: string;
  description: string;
  cycle: SyncTaskCycle;
  autoSync: boolean;
  dailyRunCount: number;
  runTimes: string[];
  weekDays: string[];
  timeoutSeconds: number;
  maxFailureTimes: number;
  duplicatePolicy: string;
  retryEnabled: boolean;
  retryTimes: number;
  retryInterval: string;
  notificationScenes: string[];
  notificationChannels: string[];
  notificationTargets: string;
}

const weekDayOptions = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const notificationSceneOptions = ["失败", "部分成功", "超时", "恢复成功"];
const notificationChannelOptions = ["站内信", "飞书", "邮件"];

function SyncTaskConfigDrawer({
  open,
  task,
  modules,
  onClose,
  onSave,
}: SyncTaskConfigDrawerProps) {
  const [form] = Form.useForm<SyncTaskConfigFormValues>();
  const cycle = Form.useWatch("cycle", form);

  useEffect(() => {
    if (!open || !task) return;
    form.setFieldsValue({
      taskName: task.taskName,
      module: task.module,
      interfaceName: task.interfaceName,
      description: task.description,
      cycle: task.cycle,
      autoSync: task.autoSync,
      dailyRunCount: task.dailyRunCount,
      runTimes: task.runTimes,
      weekDays: task.weekDays,
      timeoutSeconds: task.timeoutSeconds,
      maxFailureTimes: task.maxFailureTimes,
      duplicatePolicy: task.duplicatePolicy,
      retryEnabled: task.retryEnabled,
      retryTimes: task.retryTimes,
      retryInterval: task.retryInterval,
      notificationScenes: task.notificationScenes,
      notificationChannels: task.notificationChannels,
      notificationTargets: task.notificationTargets,
    });
  }, [form, open, task]);

  const submit = (values: SyncTaskConfigFormValues) => {
    if (!task) return;
    onSave({
      ...task,
      taskName: values.taskName,
      module: values.module,
      interfaceName: values.interfaceName,
      description: values.description,
      cycle: values.cycle,
      autoSync: values.autoSync,
      frequency: values.cycle === "周任务"
        ? `${values.weekDays.join("、") || "每周"} ${values.runTimes[0] ?? "04:00"}`
        : values.cycle === "手动任务"
          ? "手动触发"
          : values.runTimes.length > 0
            ? `每天 ${values.runTimes.join("、")}`
            : task.frequency,
      nextRunAt: values.autoSync ? task.nextRunAt ?? "2026-09-13 00:00" : undefined,
      lastStatus: values.autoSync && task.lastStatus === "已停用" ? "成功" : task.lastStatus,
      dailyRunCount: values.dailyRunCount,
      runTimes: values.runTimes,
      weekDays: values.weekDays,
      timeoutSeconds: values.timeoutSeconds,
      maxFailureTimes: values.maxFailureTimes,
      duplicatePolicy: values.duplicatePolicy,
      retryEnabled: values.retryEnabled,
      retryTimes: values.retryTimes,
      retryInterval: values.retryInterval,
      notificationScenes: values.notificationScenes,
      notificationChannels: values.notificationChannels,
      notificationTargets: values.notificationTargets,
    });
  };

  return (
    <Drawer
      className="sync-task__config-drawer"
      title="配置同步任务"
      width={680}
      open={open}
      destroyOnClose
      onClose={onClose}
      extra={(
        <Typography.Text type="secondary">
          {task ? task.taskName : "未选择任务"}
        </Typography.Text>
      )}
    >
      <Form
        form={form}
        layout="vertical"
        className="sync-task__config-form"
        onFinish={submit}
      >
        <section className="sync-task__drawer-section">
          <h3>基础信息</h3>
          <div className="sync-task__form-grid">
            <Form.Item name="taskName" label="任务名称" rules={[{ required: true, message: "请输入任务名称" }]}>
              <Input placeholder="请输入任务名称" />
            </Form.Item>
            <Form.Item name="module" label="所属模块" rules={[{ required: true, message: "请选择所属模块" }]}>
              <Select options={modules.map((module) => ({ label: module, value: module }))} />
            </Form.Item>
            <Form.Item name="interfaceName" label="接口名称" rules={[{ required: true, message: "请输入接口名称" }]}>
              <Input placeholder="请输入接口名称" />
            </Form.Item>
            <Form.Item name="description" label="任务描述" className="sync-task__form-grid-full">
              <Input.TextArea rows={3} placeholder="请输入任务描述" />
            </Form.Item>
          </div>
        </section>

        <section className="sync-task__drawer-section">
          <h3>执行计划</h3>
          <div className="sync-task__form-grid">
            <Form.Item name="cycle" label="任务周期" rules={[{ required: true, message: "请选择任务周期" }]}>
              <Radio.Group
                options={[
                  { label: "日任务", value: "日任务" },
                  { label: "周任务", value: "周任务" },
                  { label: "手动任务", value: "手动任务" },
                ]}
              />
            </Form.Item>
            <Form.Item name="autoSync" label="自动同步" valuePropName="checked">
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            </Form.Item>
            {cycle !== "手动任务" && (
              <>
                <Form.Item name="dailyRunCount" label="每天执行次数" rules={[{ required: true, message: "请输入执行次数" }]}>
                  <InputNumber min={1} max={144} addonAfter="次" />
                </Form.Item>
                <Form.Item name="runTimes" label="执行时间点" rules={[{ required: true, message: "请至少填写一个时间点" }]}>
                  <Select mode="tags" placeholder="例如 08:00、14:00、22:00" tokenSeparators={[",", "，", " "]} />
                </Form.Item>
              </>
            )}
            {cycle === "周任务" && (
              <Form.Item name="weekDays" label="周任务日期" className="sync-task__form-grid-full">
                <Select
                  mode="multiple"
                  options={weekDayOptions.map((value) => ({ label: value, value }))}
                  placeholder="请选择周任务日期"
                />
              </Form.Item>
            )}
          </div>
        </section>

        <section className="sync-task__drawer-section">
          <h3>执行限制</h3>
          <div className="sync-task__form-grid">
            <Form.Item name="timeoutSeconds" label="执行超时" rules={[{ required: true, message: "请输入超时时间" }]}>
              <InputNumber min={30} max={7_200} addonAfter="秒" />
            </Form.Item>
            <Form.Item name="maxFailureTimes" label="最大失败次数" rules={[{ required: true, message: "请输入最大失败次数" }]}>
              <InputNumber min={1} max={10} addonAfter="次" />
            </Form.Item>
            <Form.Item name="duplicatePolicy" label="运行中重复触发" className="sync-task__form-grid-full">
              <Select
                options={["忽略本次触发", "排队等待", "强制失败"].map((value) => ({ label: value, value }))}
              />
            </Form.Item>
          </div>
        </section>

        <section className="sync-task__drawer-section">
          <h3>失败重试</h3>
          <div className="sync-task__form-grid">
            <Form.Item name="retryEnabled" label="开启重试" valuePropName="checked">
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            </Form.Item>
            <Form.Item name="retryTimes" label="重试次数">
              <InputNumber min={0} max={10} addonAfter="次" />
            </Form.Item>
            <Form.Item name="retryInterval" label="重试间隔" className="sync-task__form-grid-full">
              <Input placeholder="例如 10 分钟" />
            </Form.Item>
          </div>
        </section>

        <section className="sync-task__drawer-section">
          <h3>通知设置</h3>
          <Form.Item name="notificationScenes" label="通知场景">
            <Select
              mode="multiple"
              options={notificationSceneOptions.map((value) => ({ label: value, value }))}
            />
          </Form.Item>
          <Form.Item name="notificationChannels" label="通知方式">
            <Select
              mode="multiple"
              options={notificationChannelOptions.map((value) => ({ label: value, value }))}
            />
          </Form.Item>
          <Form.Item name="notificationTargets" label="通知对象">
            <Input placeholder="请输入通知对象" />
          </Form.Item>
        </section>

        <div className="sync-task__drawer-actions">
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={() => form.submit()}>保存配置</Button>
        </div>
      </Form>
    </Drawer>
  );
}

export default SyncTaskConfigDrawer;

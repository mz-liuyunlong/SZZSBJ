import { Button, Drawer, Radio, Space, Tag, Typography } from "antd";
import { useState } from "react";
import type { SyncScheduleItem, SyncScheduleTab, SyncTaskStatus } from "@/pages/data-center/syncTaskTypes";

interface SyncTaskScheduleDrawerProps {
  open: boolean;
  initialTab: SyncScheduleTab;
  dayItems: SyncScheduleItem[];
  weekItems: SyncScheduleItem[];
  onClose: () => void;
  onOpenGlobalLog: () => void;
}

const statusColors: Record<SyncTaskStatus, string> = {
  成功: "success",
  失败: "error",
  运行中: "processing",
  部分成功: "warning",
  超时: "orange",
  已停用: "default",
};

function ScheduleTimeline({ items }: { items: SyncScheduleItem[] }) {
  return (
    <div className="sync-task__timeline">
      {items.map((item) => (
        <div key={item.id} className="sync-task__time-row">
          <div className="sync-task__time">{item.time}</div>
          <div>
            <div className="sync-task__time-title">{item.taskName}</div>
            <div className="sync-task__time-sub">
              {item.frequency} · {item.module} · {item.status}
            </div>
          </div>
          <Tag color={statusColors[item.status]}>{item.status}</Tag>
        </div>
      ))}
    </div>
  );
}

function WeeklyList({ items, weeklyOnly }: { items: SyncScheduleItem[]; weeklyOnly?: boolean }) {
  return (
    <div className="sync-task__week-list">
      {items.map((item) => (
        <div key={item.id} className="sync-task__week-row">
          <strong>{weeklyOnly ? item.taskName : `${item.weekDay ?? "周任务"} ${item.time} · ${item.taskName}`}</strong>
          <div className="sync-task__time-sub">
            {weeklyOnly ? item.frequency : `${item.module} · ${item.frequency}`} · 自动同步
          </div>
        </div>
      ))}
    </div>
  );
}

function SyncTaskScheduleDrawer({
  open,
  initialTab,
  dayItems,
  weekItems,
  onClose,
  onOpenGlobalLog,
}: SyncTaskScheduleDrawerProps) {
  const [tabOverride, setTabOverride] = useState<{
    initialTab: SyncScheduleTab;
    activeTab: SyncScheduleTab;
  }>();
  const activeTab = tabOverride?.initialTab === initialTab
    ? tabOverride.activeTab
    : initialTab;

  const closeDrawer = () => {
    setTabOverride(undefined);
    onClose();
  };

  const openGlobalLog = () => {
    setTabOverride(undefined);
    onOpenGlobalLog();
  };

  return (
    <Drawer
      className="sync-task__schedule-drawer"
      title="同步日程"
      width={560}
      open={open}
      destroyOnClose
      onClose={closeDrawer}
      footer={(
        <Space className="sync-task__drawer-footer">
          <Button onClick={openGlobalLog}>查看全局日志</Button>
          <Button onClick={closeDrawer}>关闭</Button>
        </Space>
      )}
    >
      <div className="sync-task__schedule-toolbar">
        <Radio.Group
          optionType="button"
          buttonStyle="solid"
          value={activeTab}
          options={[
            { label: "今日安排", value: "day" },
            { label: "本周安排", value: "week" },
            { label: "只看周任务", value: "weeklyOnly" },
          ]}
          onChange={(event) => setTabOverride({
            initialTab,
            activeTab: event.target.value as SyncScheduleTab,
          })}
        />
        <Typography.Text type="secondary">展示所有同步任务的计划触发时间</Typography.Text>
      </div>
      {activeTab === "day" && <ScheduleTimeline items={dayItems} />}
      {activeTab === "week" && <WeeklyList items={weekItems} />}
      {activeTab === "weeklyOnly" && <WeeklyList items={weekItems} weeklyOnly />}
    </Drawer>
  );
}

export default SyncTaskScheduleDrawer;

/** Every settings write asks for a reason (and an effective date for rule versions). */
import { ModalForm, ProFormDatePicker, ProFormTextArea } from "@ant-design/pro-components";
import dayjs, { type Dayjs } from "dayjs";
import { today } from "./settingsShared";

export interface ReasonAsk {
  title: string;
  withDate?: boolean;
  run: (reason: string, effectiveDate?: string) => Promise<unknown>;
}

export default function SettingsReasonModal({
  ask,
  onClose,
  onSaved,
  onError,
}: {
  ask?: ReasonAsk;
  onClose: () => void;
  onSaved: () => void;
  onError: (error: unknown) => void;
}) {
  return (
    <ModalForm<{ reason: string; effective_date?: string }>
      open={ask !== undefined}
      title={ask?.title}
      width={480}
      initialValues={{ effective_date: today(), reason: "" }}
      modalProps={{ destroyOnClose: true, onCancel: onClose, okText: "确认保存", cancelText: "取消" }}
      onFinish={async (values) => {
        if (!ask) return false;
        try {
          await ask.run(values.reason, values.effective_date);
          onSaved();
          return true;
        } catch (error) {
          onError(error);
          return false;
        }
      }}
    >
      {ask?.withDate && (
        <ProFormDatePicker
          name="effective_date"
          label="生效日"
          rules={[{ required: true, message: "请选择生效日" }]}
          fieldProps={{ format: "YYYY-MM-DD", disabledDate: (d: Dayjs) => d.isBefore(dayjs(today()), "day") }}
          transform={(value: string | Dayjs) => ({ effective_date: dayjs(value).format("YYYY-MM-DD") })}
        />
      )}
      <ProFormTextArea
        name="reason"
        label="修改原因"
        fieldProps={{ rows: 3 }}
        rules={[{ required: true, min: 2, max: 500, message: "请填写 2–500 字的原因" }]}
      />
    </ModalForm>
  );
}

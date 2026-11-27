/** Shared report calendar: preserve the established Daily Sales picker UI. */
import { DatePicker } from "antd";
import datePickerZhCN from "antd/es/date-picker/locale/zh_CN";
import dayjs, { type Dayjs } from "dayjs";
import "dayjs/locale/zh-cn";
import updateLocale from "dayjs/plugin/updateLocale";
import type { ComponentProps } from "react";
import { disableFutureDate } from "@/shared/date/disableFutureDate";

dayjs.extend(updateLocale);
dayjs.locale("zh-cn");
dayjs.updateLocale("zh-cn", { weekStart: 0 });

const rangePresets = (): { label: string; value: [Dayjs, Dayjs] }[] => {
  const today = dayjs();
  return [
    { label: "今天", value: [today, today] },
    { label: "昨天", value: [today.subtract(1, "day"), today.subtract(1, "day")] },
    { label: "最近7天", value: [today.subtract(6, "day"), today] },
    { label: "最近30天", value: [today.subtract(29, "day"), today] },
    { label: "本月", value: [today.startOf("month"), today] },
    { label: "上月", value: [today.subtract(1, "month").startOf("month"), today.subtract(1, "month").endOf("month")] },
    { label: "本年", value: [today.startOf("year"), today] },
    { label: "去年", value: [today.subtract(1, "year").startOf("year"), today.subtract(1, "year").endOf("year")] },
  ];
};

const datePickerLocale = {
  ...datePickerZhCN,
  lang: {
    ...datePickerZhCN.lang,
    monthFormat: "M 月",
    shortWeekDays: ["日", "一", "二", "三", "四", "五", "六"],
  },
};

type Props = Omit<ComponentProps<typeof DatePicker.RangePicker>,
  "locale" | "presets" | "format" | "disabledDate" | "separator">;

export default function ReportDateRangePicker(props: Props) {
  return <DatePicker.RangePicker
    {...props}
    locale={datePickerLocale}
    presets={rangePresets()}
    format="YYYY-MM-DD"
    disabledDate={disableFutureDate}
    separator="~"
  />;
}

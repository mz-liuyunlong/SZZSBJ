import dayjs, { type Dayjs } from "dayjs";

/**
 * Global date picker guard.
 *
 * Date filters must not allow future business/log dates.
 * Today and historical dates are selectable; tomorrow and later are disabled.
 */
export const disableFutureDate = (current: Dayjs) => (
  current.isAfter(dayjs(), "day")
);

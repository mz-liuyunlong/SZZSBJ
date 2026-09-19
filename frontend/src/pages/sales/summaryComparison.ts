const MS_PER_DAY = 24 * 60 * 60 * 1000;

export interface PreviousComparableDateRange {
  startDate: string;
  endDate: string;
}

const parseYmd = (value: string) => {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;

  const [, year, month, day] = match;
  return new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
};

const formatYmd = (date: Date) => {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const addDays = (date: Date, days: number) => (
  new Date(date.getTime() + days * MS_PER_DAY)
);

/**
 * 按用户当前页面选择的日期生成对比日期。
 *
 * 例：
 * 2026-09-19 ~ 2026-09-19 -> 2026-09-18 ~ 2026-09-18
 * 2026-09-15 ~ 2026-09-19 -> 2026-09-10 ~ 2026-09-14
 */
export const previousComparableDateRange = (
  startDate?: string,
  endDate?: string,
): PreviousComparableDateRange | null => {
  if (!startDate || !endDate) return null;

  const start = parseYmd(startDate);
  const end = parseYmd(endDate);
  if (!start || !end || end < start) return null;

  const rangeDays = Math.max(
    1,
    Math.round((end.getTime() - start.getTime()) / MS_PER_DAY) + 1,
  );

  const previousEnd = addDays(start, -1);
  const previousStart = addDays(start, -rangeDays);

  return {
    startDate: formatYmd(previousStart),
    endDate: formatYmd(previousEnd),
  };
};

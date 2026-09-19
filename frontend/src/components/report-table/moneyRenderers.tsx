/** Shared money renderers for report tables.
 *
 * Display currency is a page-level preference. Source currency decides the
 * conversion direction:
 * - USD source fields: USD = value, CNY = value * fx.
 * - CNY source fields: CNY = value, USD = value / fx.
 */
import { MoneyCell } from "@/components/report-table/cells";

export type ReportDisplayCurrency = "USD" | "CNY";
export type ReportFxRate<Row extends object> = number | ((row: Row) => number | null | undefined);

const displaySymbol = (currency: ReportDisplayCurrency) => currency === "CNY" ? "¥" : "$";

const numericValue = <Row extends object>(row: Row, key: keyof Row) => {
  const value = row[key];
  return typeof value === "number" ? value : null;
};

const resolveRate = <Row extends object>(row: Row, rate: ReportFxRate<Row>) => {
  const resolved = typeof rate === "function" ? rate(row) : rate;
  return resolved && Number.isFinite(resolved) && resolved > 0 ? resolved : 1;
};

export const convertUsdSourceValue = (
  value: number | null | undefined,
  currency: ReportDisplayCurrency,
  usdToCnyRate: number,
) => {
  if (value == null || !Number.isFinite(value)) return null;
  return currency === "CNY" ? value * usdToCnyRate : value;
};

export const convertCnySourceValue = (
  value: number | null | undefined,
  currency: ReportDisplayCurrency,
  usdToCnyRate: number,
) => {
  if (value == null || !Number.isFinite(value)) return null;
  return currency === "USD" ? value / usdToCnyRate : value;
};

export const renderUsdSourceMoney = <Row extends object>(
  key: keyof Row,
  currency: ReportDisplayCurrency,
  usdToCnyRate: ReportFxRate<Row>,
) => (_: unknown, row: Row) => {
  const value = numericValue(row, key);
  const rate = resolveRate(row, usdToCnyRate);
  return <MoneyCell value={convertUsdSourceValue(value, currency, rate)} currency={displaySymbol(currency)} />;
};

export const renderCnySourceMoney = <Row extends object>(
  key: keyof Row,
  currency: ReportDisplayCurrency,
  usdToCnyRate: ReportFxRate<Row>,
) => (_: unknown, row: Row) => {
  const value = numericValue(row, key);
  const rate = resolveRate(row, usdToCnyRate);
  return <MoneyCell value={convertCnySourceValue(value, currency, rate)} currency={displaySymbol(currency)} />;
};


export const convertCnyUnitTotalOrUsdSourceValue = (
  usdTotal: number | null,
  cnyUnit: number | null,
  quantity: number | null,
  currency: ReportDisplayCurrency,
  usdToCnyRate: number,
) => {
  if (currency === "CNY") {
    if (cnyUnit != null && quantity != null) {
      return cnyUnit * quantity;
    }

    return convertUsdSourceValue(usdTotal, currency, usdToCnyRate);
  }

  return convertUsdSourceValue(usdTotal, currency, usdToCnyRate);
};

export const renderCnyUnitTotalOrUsdSourceMoney = <Row extends object>(
  usdTotalKey: keyof Row,
  cnyUnitKey: keyof Row,
  quantityKey: keyof Row,
  currency: ReportDisplayCurrency,
  usdToCnyRate: number | ((row: Row) => number),
) => (_: unknown, row: Row) => {
  const usdTotal = numericValue(row, usdTotalKey);
  const cnyUnit = numericValue(row, cnyUnitKey);
  const quantity = numericValue(row, quantityKey);
  const rate = resolveRate(row, usdToCnyRate);

  return (
    <MoneyCell
      value={convertCnyUnitTotalOrUsdSourceValue(usdTotal, cnyUnit, quantity, currency, rate)}
      currency={displaySymbol(currency)}
    />
  );
};

export const dynamicCurrencyTitle = (
  base: string,
  currency: ReportDisplayCurrency,
) => `${base}(${displaySymbol(currency)})`;

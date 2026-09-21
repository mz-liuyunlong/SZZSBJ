/** Provides small report-table cells shared by existing no-API data pages. */
import { CheckOutlined, CopyOutlined, PictureOutlined } from "@ant-design/icons";
import { Button, Popover, Space, Tag, Tooltip } from "antd";
import ReactECharts from "echarts-for-react";
import { useState, type MouseEvent, type ReactNode } from "react";
import "@/components/report-table/reportTable.css";

interface CopyableTextCellProps {
  text: string;
  label: string;
  link?: boolean;
  onCopy?: (text: string) => void;
  onOpen?: () => void;
}

async function copyTextWithFallback(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "-9999px";

  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

export function CopyableTextCell({ text, label, link, onCopy, onOpen }: CopyableTextCellProps) {
  const [copied, setCopied] = useState(false);

  const copy = async (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();

    try {
      if (onCopy) {
        onCopy(text);
      } else {
        await copyTextWithFallback(text);
      }

      setCopied(true);
      window.setTimeout(() => setCopied(false), 900);
    } catch {
      setCopied(false);
    }
  };

  return (
    <span className="report-table-copyable" data-copyable-text={text}>
      <Tooltip title={text}>
        {link ? (
          <Button className="report-table-copyable__link" type="link" onClick={onOpen}>
            {text}
          </Button>
        ) : (
          <span className="report-table-copyable__text">{text}</span>
        )}
      </Tooltip>
      <Tooltip title={copied ? `已复制${label}` : `复制${label}`}>
        <Button
          className={copied ? "report-table-copyable__button report-table-copyable__button--copied" : "report-table-copyable__button"}
          type="text"
          size="small"
          aria-label={`复制${label}：${text}`}
          icon={copied ? <CheckOutlined aria-hidden="true" /> : <CopyOutlined aria-hidden="true" />}
          onClick={copy}
        />
      </Tooltip>
    </span>
  );
}



const WALMART_ITEM_URL_PREFIX = "https://www.walmart.com/ip/";

const walmartItemUrl = (productId: string) => {
  const normalized = productId.trim();
  return `${WALMART_ITEM_URL_PREFIX}${encodeURIComponent(normalized)}`;
};

const openWalmartItem = (productId: string) => {
  const normalized = productId.trim();
  if (!normalized || normalized === "-") return;

  const opened = window.open(walmartItemUrl(normalized), "_blank", "noopener,noreferrer");
  if (opened) opened.opener = null;
};

interface WalmartProductIdCellProps {
  productId: string;
  onCopy?: (text: string) => void;
}

export function WalmartProductIdCell({ productId, onCopy }: WalmartProductIdCellProps) {
  return (
    <span className="report-table-product-id-cell">
      <CopyableTextCell
        text={productId}
        label="商品ID"
        link
        onCopy={onCopy}
        onOpen={() => openWalmartItem(productId)}
      />
    </span>
  );
}

interface ProductIdentityCellProps {
  productId: string;
  productName: string;
  onCopy?: (text: string) => void;
}

export function ProductIdentityCell({
  productId,
  productName,
  onCopy,
}: ProductIdentityCellProps) {
  return (
    <Space direction="vertical" size={0} className="report-table-identity-stack">
      <WalmartProductIdCell productId={productId} onCopy={onCopy} />
      <CopyableTextCell text={productName} label="品名" onCopy={onCopy} />
    </Space>
  );
}

interface SkuMskuIdentityCellProps {
  sku: string;
  msku: string;
  onCopy?: (text: string) => void;
}

export function SkuMskuIdentityCell({ sku, msku, onCopy }: SkuMskuIdentityCellProps) {
  return (
    <Space direction="vertical" size={0} className="report-table-identity-stack">
      <CopyableTextCell text={sku} label="SKU" onCopy={onCopy} />
      <CopyableTextCell text={msku} label="MSKU" onCopy={onCopy} />
    </Space>
  );
}



interface ImageCellProps {
  image?: string;
  src?: string;
  previewSrc?: string;
  alt?: string;
  label?: string;
  thumbnailSize?: number;
  previewSize?: number;
  fallback?: ReactNode;
  placement?: "top" | "bottom" | "left" | "right";
}

function ImageVisual({
  src,
  alt,
  size,
  fallback,
}: Pick<ImageCellProps, "src" | "alt" | "fallback"> & { size: number }) {
  const [failed, setFailed] = useState(false);
  if (src && !failed) {
    return (
      <img
        src={src}
        alt={alt}
        width={size}
        height={size}
        loading="lazy"
        decoding="async"
        onError={() => setFailed(true)}
      />
    );
  }
  return <span className="report-table-image__fallback">{fallback ?? <PictureOutlined aria-hidden="true" />}</span>;
}

const imageSourcePattern = /^(https?:\/\/|data:image\/|blob:|\/|\.{1,2}\/)/i;

function resolveImageCellSource(image?: string, explicitSrc?: string) {
  if (explicitSrc) return explicitSrc;
  if (!image) return undefined;
  return imageSourcePattern.test(image) ? image : undefined;
}

export function ImageCell({
  image,
  src,
  previewSrc,
  alt = "商品图片",
  label = "图片占位",
  thumbnailSize = 36,
  previewSize = 260,
  fallback,
  placement = "right",
}: ImageCellProps) {
  const resolvedSrc = resolveImageCellSource(image, src);
  const resolvedPreviewSrc = resolveImageCellSource(previewSrc) ?? resolvedSrc;
  const resolvedFallback = fallback ?? (resolvedSrc ? undefined : image);

  return (
    <Popover
      trigger={["hover", "focus"]}
      placement={placement}
      content={(
        <span className="report-table-image-preview" style={{ width: previewSize, height: previewSize }}>
          <ImageVisual
            key={`preview:${resolvedPreviewSrc ?? "fallback"}`}
            src={resolvedPreviewSrc}
            alt={alt}
            size={previewSize}
            fallback={resolvedFallback}
          />
        </span>
      )}
    >
      <span
        className="report-table-image"
        aria-label={label}
        tabIndex={0}
        style={{ width: thumbnailSize, height: thumbnailSize }}
      >
        <ImageVisual
          key={`thumbnail:${resolvedSrc ?? "fallback"}`}
          src={resolvedSrc}
          alt={alt}
          size={thumbnailSize}
          fallback={resolvedFallback}
        />
      </span>
    </Popover>
  );
}


interface TrendPreviewCellProps {
  values: number[];
  dates: string[];
  label?: string;
}

interface TrendTooltipParam {
  axisValue?: string;
  axisValueLabel?: string;
  data?: number | string;
  value?: number | string;
}

const formatTrendNumber = (value: number | string | null | undefined) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return Math.round(numeric).toLocaleString("zh-CN");
};

const formatTrendAverage = (value: number) => (
  Number.isFinite(value)
    ? value.toFixed(1).replace(/\.0$/, "")
    : "0"
);

const formatTrendDate = (value: string) => (
  value.length >= 10 ? value.slice(5) : value
);

const normalizeTrendDates = (values: number[], dates: string[]) => {
  if (dates.length >= values.length) return dates.slice(0, values.length);

  return values.map((_, index) => dates[index] ?? `第${index + 1}天`);
};

export function TrendPreviewCell({ values, dates, label = "销量" }: TrendPreviewCellProps) {
  const safeValues = values.map((value) => (Number.isFinite(value) ? value : 0));
  const safeDates = normalizeTrendDates(safeValues, dates);

  const max = Math.max(...safeValues, 0);
  const min = Math.min(...safeValues, max);
  const average = safeValues.reduce((sum, value) => sum + value, 0) / Math.max(safeValues.length, 1);
  const yAxisMax = Math.max(21, Math.ceil(Math.max(max, 1) / 3) * 3);
  const yAxisInterval = yAxisMax <= 21 ? 3 : Math.max(1, Math.ceil(yAxisMax / 7));

  const points = safeValues
    .map((value, index) => `${index * 15},${30 - value / Math.max(max, 1) * 26}`)
    .join(" ");

  const tooltipFormatter = (params: TrendTooltipParam[] | TrendTooltipParam) => {
    const first = Array.isArray(params) ? params[0] : params;
    const date = first?.axisValueLabel ?? first?.axisValue ?? "";
    const value = first?.data ?? first?.value;

    return `
      <div class="report-table-trend-tooltip">
        <div class="report-table-trend-tooltip__date">${date}</div>
        <div class="report-table-trend-tooltip__row">
          <span>${label}</span>
          <strong>${formatTrendNumber(value)}</strong>
        </div>
      </div>
    `;
  };

  const option = {
    animationDuration: 180,
    title: { text: label, show: false },
    grid: { left: 38, right: 18, top: 38, bottom: 56 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#152033",
      borderWidth: 0,
      padding: [8, 10],
      textStyle: { color: "#fff", fontSize: 12 },
      axisPointer: {
        type: "shadow",
        shadowStyle: { color: "rgba(22,119,255,.035)" },
      },
      formatter: tooltipFormatter,
    },
    xAxis: {
      type: "category",
      data: safeDates,
      boundaryGap: false,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#dce5ef" } },
      axisLabel: {
        color: "#7d8898",
        formatter: (value: string) => formatTrendDate(value),
      },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: yAxisMax,
      interval: yAxisInterval,
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: "#8a95a6" },
      splitLine: { lineStyle: { color: "#edf2f7" } },
    },
    series: [
      {
        name: label,
        type: "line",
        data: safeValues,
        smooth: 0.34,
        symbol: "circle",
        symbolSize: 7,
        lineStyle: { width: 2.4, color: "#1677ff" },
        itemStyle: { color: "#fff", borderColor: "#1677ff", borderWidth: 2 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(22,119,255,.18)" },
              { offset: 0.6, color: "rgba(22,119,255,.05)" },
              { offset: 1, color: "rgba(22,119,255,0)" },
            ],
          },
        },
        label: {
          show: true,
          position: "top",
          distance: 6,
          formatter: (params: { value: number | string }) => `{n|${formatTrendNumber(params.value)}}`,
          rich: {
            n: {
              color: "#344054",
              fontSize: 11,
              fontWeight: 800,
              backgroundColor: "rgba(255,255,255,.96)",
              borderColor: "#dce6f1",
              borderWidth: 1,
              borderRadius: 6,
              padding: [2, 5],
            },
          },
        },
        markArea: {
          silent: true,
          itemStyle: { color: "rgba(36,180,126,.035)" },
          data: [[{ yAxis: Math.max(0, average - 1) }, { yAxis: average + 1 }]],
        },
      },
    ],
    dataZoom: [
      { type: "inside", zoomLock: true },
      {
        type: "slider",
        height: 12,
        bottom: 5,
        borderColor: "transparent",
        backgroundColor: "#f3f6fa",
        fillerColor: "rgba(22,119,255,.10)",
        showDetail: false,
      },
    ],
  };

  return (
    <Popover
      trigger={["hover", "focus"]}
      placement="right"
      classNames={{ root: "report-table-trend-popover" }}
      content={(
        <section className="report-table-trend-popover__card" aria-label={`前 7 天${label}趋势`}>
          <div className="report-table-trend-popover__head">
            <div className="report-table-trend-popover__titlebox">
              <span className="report-table-trend-popover__bar" aria-hidden="true" />
              <div>
                <div className="report-table-trend-popover__title">前 7 天{label}趋势</div>
                <div className="report-table-trend-popover__sub">趋势区间 + 每日值标签</div>
              </div>
            </div>

            <div className="report-table-trend-popover__summary" aria-label="趋势摘要">
              <span className="report-table-trend-popover__pill">最高 <b>{formatTrendNumber(max)}</b></span>
              <span className="report-table-trend-popover__pill">最低 <b>{formatTrendNumber(min)}</b></span>
              <span className="report-table-trend-popover__pill">日均 <b>{formatTrendAverage(average)}</b></span>
            </div>
          </div>

          <div className="report-table-trend-popover__wrap">
            <ReactECharts
              className="report-table-trend-popover__chart"
              option={option}
              notMerge
              lazyUpdate
            />
          </div>
        </section>
      )}
    >
      <svg
        className="report-table-trend-cell"
        viewBox="0 0 90 32"
        role="img"
        aria-label="前7天销量趋势图"
        tabIndex={0}
      >
        <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" />
      </svg>
    </Popover>
  );
}

export type MoneyCellTone = "default" | "profit";

const moneyToneClass = (
  value: number,
  tone: MoneyCellTone,
) => {
  if (tone !== "profit") return "";
  if (value > 0) return " report-table-metric--profit-positive";
  if (value < 0) return " report-table-metric--profit-negative";
  return " report-table-metric--profit-neutral";
};

export function MoneyCell({
  value,
  currency = "$",
  tone = "default",
}: {
  value: number | null | undefined;
  currency?: "$" | "¥";
  tone?: MoneyCellTone;
}) {
  if (value == null || !Number.isFinite(value)) {
    return <span className="report-table-metric">—</span>;
  }

  return (
    <span className={`report-table-metric${moneyToneClass(value, tone)}`}>
      {currency}{value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
    </span>
  );
}

export function PercentCell({ value }: { value: number | null | undefined }) {
  if (value == null || !Number.isFinite(value)) {
    return <span className="report-table-metric">—</span>;
  }
  return <span className="report-table-metric">{value.toFixed(2)}%</span>;
}

export function StatusTagCell({ label, color }: { label: string; color: string }) {
  return <Tag color={color}>{label}</Tag>;
}

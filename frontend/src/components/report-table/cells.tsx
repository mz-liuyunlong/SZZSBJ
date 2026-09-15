/** Provides small report-table cells shared by existing no-API data pages. */
import { CheckOutlined, CopyOutlined, PictureOutlined } from "@ant-design/icons";
import { Button, Popover, Tag, Tooltip } from "antd";
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

export function TrendPreviewCell({ values, dates, label = "销量" }: TrendPreviewCellProps) {
  const max = Math.max(...values, 1);
  const points = values.map((value, index) => `${index * 15},${30 - value / max * 26}`).join(" ");
  const average = values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1);
  const option = {
    animationDuration: 180,
    grid: { top: 34, right: 44, bottom: 58, left: 48 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: dates, axisLabel: { fontSize: 12 } },
    yAxis: { type: "value", name: label, axisLabel: { fontSize: 12 } },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 14, bottom: 10 }],
    series: [{
      type: "line",
      data: values,
      smooth: true,
      symbol: "circle",
      symbolSize: 7,
      lineStyle: { width: 2, color: "#1677ff" },
      itemStyle: { color: "#1677ff" },
      label: { show: true, position: "top", fontSize: 12 },
      markLine: {
        symbol: "none",
        lineStyle: { color: "#20b486", type: "dashed" },
        label: { formatter: Math.round(average).toString(), position: "end" },
        data: [{ yAxis: average }],
      },
    }],
  };

  return (
    <Popover
      trigger={["hover", "focus"]}
      placement="right"
      title="前 7 天销量趋势"
      content={<ReactECharts className="report-table-trend-preview" option={option} notMerge lazyUpdate />}
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

export function MoneyCell({ value, currency = "$" }: { value: number; currency?: "$" | "¥" }) {
  return (
    <span className="report-table-metric">
      {currency}{value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
    </span>
  );
}

export function PercentCell({ value }: { value: number }) {
  return <span className="report-table-metric">{value.toFixed(2)}%</span>;
}

export function StatusTagCell({ label, color }: { label: string; color: string }) {
  return <Tag color={color}>{label}</Tag>;
}

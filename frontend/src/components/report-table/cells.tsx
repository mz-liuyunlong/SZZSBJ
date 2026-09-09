/** Provides small report-table cells shared by existing no-API data pages. */
import { CopyOutlined, PictureOutlined } from "@ant-design/icons";
import { Button, Popover, Tag, Tooltip } from "antd";
import ReactECharts from "echarts-for-react";
import { useState, type MouseEvent, type ReactNode } from "react";
import "./reportTable.css";

interface CopyableTextCellProps {
  text: string;
  label: string;
  link?: boolean;
  onCopy: (text: string) => void;
  onOpen?: () => void;
}

export function CopyableTextCell({ text, label, link, onCopy, onOpen }: CopyableTextCellProps) {
  const copy = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    onCopy(text);
  };

  return (
    <span className="report-table-copyable">
      <Tooltip title={text}>
        {link ? (
          <Button className="report-table-copyable__link" type="link" onClick={onOpen}>
            {text}
          </Button>
        ) : (
          <span className="report-table-copyable__text">{text}</span>
        )}
      </Tooltip>
      <Button
        className="report-table-copyable__button"
        type="text"
        size="small"
        aria-label={`复制${label}：${text}`}
        icon={<CopyOutlined aria-hidden="true" />}
        onClick={copy}
      />
    </span>
  );
}

interface ImageCellProps {
  src?: string;
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
    return <img src={src} alt={alt} width={size} height={size} onError={() => setFailed(true)} />;
  }
  return <span className="report-table-image__fallback">{fallback ?? <PictureOutlined aria-hidden="true" />}</span>;
}

export function ImageCell({
  src,
  alt = "商品图片",
  label = "图片占位",
  thumbnailSize = 36,
  previewSize = 260,
  fallback,
  placement = "right",
}: ImageCellProps) {
  return (
    <Popover
      trigger={["hover", "focus"]}
      placement={placement}
      content={(
        <span className="report-table-image-preview" style={{ width: previewSize, height: previewSize }}>
          <ImageVisual src={src} alt={alt} size={previewSize} fallback={fallback} />
        </span>
      )}
    >
      <span
        className="report-table-image"
        aria-label={label}
        tabIndex={0}
        style={{ width: thumbnailSize, height: thumbnailSize }}
      >
        <ImageVisual src={src} alt={alt} size={thumbnailSize} fallback={fallback} />
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

/** 财务页面统一框架：与 PMC 采购看板同一套（page card / 标题行 / 筛选卡 / 统计卡 / 表格区）。 */
import { Card, Tag, Tooltip } from "antd";
import type { ReactNode } from "react";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import { MoneyCell } from "@/components/report-table/cells";
import { usePreviewMeta } from "@/pages/finance/localFinData";
import "@/pages/finance/finance.css";

interface FinanceBoardFrameProps {
  title: string;
  subtitle?: ReactNode;
  loading?: boolean;
  toolbar?: ReactNode;
  summary?: ReactNode;
  children?: ReactNode;
}

export function PreviewTag() {
  const meta = usePreviewMeta();
  return (
    <Tooltip title={`本地预览：数据为 Demo 构建快照${meta.data ? `（导出于 ${meta.data.exported_at}）` : ""}，只读，不保存任何操作；操作按钮在正式接口上线后开放`}>
      <Tag color="gold" bordered={false}>本地预览 · 只读</Tag>
    </Tooltip>
  );
}

export const LOCKED_TIP = "本地预览只读：正式接口上线后可用";

/** 金额：CNY / USD 用共享 MoneyCell；CNH 等其他币种带币种前缀；masked 显示 ****。 */
export function FinMoney({ value, cur = "CNY", masked }: { value: number | null | undefined; cur?: string; masked?: boolean }) {
  if (masked) return <span className="report-table-metric">****</span>;
  if (cur === "CNY" || cur === "USD") return <MoneyCell value={value} currency={cur === "USD" ? "$" : "¥"} />;
  if (value == null || !Number.isFinite(value)) return <span className="report-table-metric">—</span>;
  return <span className={`report-table-metric${value < 0 ? " finance-board__metric--neg" : ""}`}>{cur} {value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>;
}

function FinanceBoardFrame({ title, subtitle, loading, toolbar, summary, children }: FinanceBoardFrameProps) {
  return (
    <div className="finance-board">
      <Card size="small" className="finance-board__page-card">
        <RequestLoadingOverlay spinning={Boolean(loading)} label="正在加载，请稍候" />
        <div className="finance-board__title-row">
          <div>
            <h1>{title}</h1>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <PreviewTag />
        </div>
        {toolbar && <Card size="small" className="finance-board__toolbar-card"><div className="finance-board__toolbar">{toolbar}</div></Card>}
        {summary}
        <div className="finance-board__table-wrap">{children}</div>
      </Card>
    </div>
  );
}

export default FinanceBoardFrame;

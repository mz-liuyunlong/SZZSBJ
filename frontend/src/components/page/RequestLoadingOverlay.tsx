import { Spin } from "antd";
import "@/components/page/RequestLoadingOverlay.css";

interface RequestLoadingOverlayProps {
  spinning: boolean;
  label?: string;
  className?: string;
}

function RequestLoadingOverlay({
  spinning,
  label = "正在加载数据，请稍候",
  className,
}: RequestLoadingOverlayProps) {
  if (!spinning) return null;

  return (
    <div
      className={["request-loading-overlay", className].filter(Boolean).join(" ")}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <Spin size="large" tip={label}>
        <div className="request-loading-overlay__placeholder" />
      </Spin>
    </div>
  );
}

export default RequestLoadingOverlay;

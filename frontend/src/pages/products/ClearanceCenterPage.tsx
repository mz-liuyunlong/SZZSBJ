/** V4 clearance UI preview. This route never calls a production API. */
import { Alert } from "antd";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import "./ClearanceCenterPage.css";

export default function ClearanceCenterPage({ page }: { page: NavigationPage }) {
  return <PageShell page={page}>
    <div className="clearance-center-preview">
      <Alert showIcon type="info" className="clearance-center-preview__notice"
        message="WFS 清货中心 V4 · 演示模式"
        description="模拟 SKU、浏览器本地记录及模拟审批；未接入真实库存、审批工作台或规则服务，不会执行平台操作。" />
      <iframe title="WFS 清货中心 V4 规则配置演示"
        className="clearance-center-preview__frame"
        src="/demos/wfs-clearance-center-v4.html"
        sandbox="allow-scripts allow-same-origin allow-modals allow-downloads"
        referrerPolicy="no-referrer" />
    </div>
  </PageShell>;
}

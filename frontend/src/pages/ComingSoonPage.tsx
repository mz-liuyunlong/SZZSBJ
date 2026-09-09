/** Provides the single no-API placeholder for navigation pages that are not ready. */
import { Result } from "antd";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";

interface ComingSoonPageProps {
  page: NavigationPage;
}

function ComingSoonPage({ page }: ComingSoonPageProps) {
  return (
    <PageShell
      page={page}
      description={`${page.title}当前仅提供页面结构，尚未接入业务功能。`}
    >
      <Result
        status="info"
        title="功能建设中"
        subTitle="此页面暂不请求业务数据，也不提供业务操作。"
      />
    </PageShell>
  );
}

export default ComingSoonPage;

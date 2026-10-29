import { Result } from "antd";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import type { AuthUser } from "@/pages/auth/authTypes";

interface Props {
  page: NavigationPage;
  user: AuthUser;
}

export default function DashboardHomePage({ page }: Props) {
  return (
    <PageShell page={page}>
      <div
        style={{
          minHeight: "calc(100vh - 210px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Result
          status="info"
          title="功能建设中"
        />
      </div>
    </PageShell>
  );
}

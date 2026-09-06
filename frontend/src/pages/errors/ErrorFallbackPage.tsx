import { Button, Result } from "antd";
import { useNavigate } from "react-router-dom";
import { DEFAULT_BUSINESS_PATH } from "../../router/routeResolver";
import "./ErrorPages.css";

interface ErrorPageProps {
  actionLabel: string;
  description: string;
  onAction: () => void;
  status: 404 | 500;
  title: string;
}

export function ErrorPage({
  actionLabel,
  description,
  onAction,
  status,
  title,
}: ErrorPageProps) {
  return (
    <main className="error-page" aria-label={`${status}错误页面`}>
      <div className="error-page__panel">
        <Result
          status={status}
          title={title}
          subTitle={description}
          extra={
            <Button type="primary" onClick={onAction}>
              {actionLabel}
            </Button>
          }
        />
      </div>
    </main>
  );
}

function ErrorFallbackPage({ onReset }: { onReset: () => void }) {
  const navigate = useNavigate();

  const returnHome = () => {
    navigate(DEFAULT_BUSINESS_PATH, { replace: true });
    onReset();
  };

  return (
    <ErrorPage
      status={500}
      title="页面暂时无法显示"
      description="前端页面发生未知错误，请返回首页后重试。"
      actionLabel="返回首页"
      onAction={returnHome}
    />
  );
}

export default ErrorFallbackPage;

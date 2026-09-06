import { useNavigate } from "react-router-dom";
import { DEFAULT_BUSINESS_PATH } from "../../router/routeResolver";
import { ErrorPage } from "./ErrorFallbackPage";

function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <ErrorPage
      status={404}
      title="页面不存在"
      description="当前地址没有对应页面，请返回首页继续使用。"
      actionLabel="返回首页"
      onAction={() => navigate(DEFAULT_BUSINESS_PATH, { replace: true })}
    />
  );
}

export default NotFoundPage;

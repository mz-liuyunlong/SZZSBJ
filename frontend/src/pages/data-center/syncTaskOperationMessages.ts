interface OperationErrorLike {
  status?: number;
  code?: string;
  message?: string;
}

const isOperationErrorLike = (value: unknown): value is OperationErrorLike => (
  typeof value === "object" && value !== null
);

const operationCodeMessages: Record<string, string> = {
  SYNC_HANDLER_NOT_EXECUTABLE: "该接口暂未接入后台执行器，目前不能从前端直接执行真实同步。请使用服务器定时脚本或查看同步日志。",
  TASK_DISPATCH_UNAVAILABLE: "后台任务派发服务暂不可用，请检查 Celery / Redis / Worker 后再试。",
  SYNC_CONFIG_DISABLED: "同步配置未启用，请先确认后端治理配置。",
  SYNC_INTERFACE_DISABLED: "接口未启用，不能执行真实同步。",
  SYNC_EXECUTION_FAILED: "后台执行失败，请查看同步日志。",
  SYNC_LOCK_LEASE_EXPIRED: "同步锁租约已过期，可能是任务运行过久或 Worker 中断。",
  SYNC_PRODUCTLIST_RESPONSE_FAILED: "ProductList 接口返回失败，请查看执行日志。",
  SYNC_PRODUCTLIST_TRANSPORT_FAILED: "ProductList 接口请求失败，请检查领星接口或网络。",
  PRODUCT_INFO_OWNER_CARDINALITY: "ProductInfo 负责人字段存在多值，当前解析规则暂不支持。",
  PRODUCT_INFO_EXECUTION_FAILED: "ProductInfo 执行失败，请查看后端日志。",
  PRODUCT_INFO_TRANSPORT_FAILED: "ProductInfo 接口请求失败，请检查领星接口或网络。",
};

export function formatSyncTaskOperationError(reason: unknown) {
  const error = isOperationErrorLike(reason) ? reason : undefined;
  const status = error?.status;
  const code = error?.code ?? error?.message ?? "";

  if (
    status === 401
    || code === "UNAUTHORIZED"
    || code === "AUTHENTICATION_REQUIRED"
    || code === "NOT_AUTHENTICATED"
  ) {
    return "当前账号未完成登录授权，暂不能执行真实同步。";
  }

  if (
    status === 403
    || code === "FORBIDDEN"
    || code === "PERMISSION_DENIED"
    || code === "INSUFFICIENT_PERMISSION"
  ) {
    return "当前账号没有同步任务操作权限，请完成授权后再试。";
  }

  if (status === 409 || code === "IDEMPOTENCY_CONFLICT") {
    return "同步操作已提交或存在重复请求，请刷新任务状态后再试。";
  }

  if (code && operationCodeMessages[code]) {
    return operationCodeMessages[code];
  }

  if (status === 503) {
    return "后台任务服务暂不可用，请稍后再试。";
  }

  if (code) {
    return `同步操作失败：${code}`;
  }

  return "同步操作失败，请稍后再试。";
}

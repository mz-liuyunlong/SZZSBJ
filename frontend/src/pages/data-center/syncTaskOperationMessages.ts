interface OperationErrorLike {
  status?: number;
  code?: string;
  message?: string;
}

const isOperationErrorLike = (value: unknown): value is OperationErrorLike => (
  typeof value === "object" && value !== null
);

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

  if (status === 503 || code === "TASK_DISPATCH_UNAVAILABLE") {
    return "后台任务派发服务暂不可用，请稍后再试。";
  }

  if (code) {
    return `同步操作失败：${code}`;
  }

  return "同步操作失败，请稍后再试。";
}

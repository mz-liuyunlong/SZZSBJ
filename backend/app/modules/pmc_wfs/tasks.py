"""WFS 创建不再有自己的 Celery 任务或定时器（Rocky 2026-11-04）。

提交、查询、重试都由 数据中心 · 任务中心 的「WFS 创建结果拉取」执行，见 ``creation_task``。
这里只保留原来的导入位置。
"""

from app.modules.pmc_wfs.creation_task import dispatch_creation, get_creation_dispatcher

__all__ = ["dispatch_creation", "get_creation_dispatcher"]

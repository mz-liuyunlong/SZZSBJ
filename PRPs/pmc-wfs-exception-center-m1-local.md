# WFS 异常中心 M1-local PRP

状态：**已批准**（2026-10-29 用户 Q1–Q7 确认）  
决策：`docs/data-sources/decisions/pmc-wfs-exception-center-decision.md`  
需求：`docs/delivery/wfs-v2-requirements/03-异常中心开发需求.md`

## 交付

- Alembic：`ops_wfs_exception_cases`、`evt_wfs_exception_detections`、`evt_wfs_exception_actions`
- API 前缀 `/api/pmc/wfs/exception-center`：cases 列表/详情/summary/filter-options；POST assign；POST events
- 权限：`page:pmc:wfs:view`；`action:pmc:wfs-exceptions:assign`；`action:pmc:wfs-exceptions:handle`
- 前端：异常中心列表 + 处理抽屉；枚举对齐 V2.0；看板抽屉关联异常占位
- 文档：API md、SOP、DATA_INTERFACE_REGISTRY；pytest + 前端 smoke test

## 非范围

自动六类规则、领星读模型、设置联动、附件、通知、Tab 侧栏徽标（summary 口径先供页面标题）

## 回滚

关闭路由注册；保留表与只读查询能力。

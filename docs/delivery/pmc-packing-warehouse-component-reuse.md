# 仓库页面组件复用

本轮复用项目 ReportTableShell、ResizableColumnTitle、CopyableTextCell、WalmartItemLink、usePageStateCache、backendRequest、登录权限查询、React Query、现有国内仓页面入口与 Ant Design 表单/弹窗。保留既有审批页面并发改动。新增的仓库装箱/测量/详情组件仅服务本模块，无新状态库或UI框架。

测试边界：Playwright仓库结构及仓库真实本地回滚接口联调；pytest仅仓库模块；TypeScript编译及仓库目录ESLint。当前不运行全局E2E/全局业务回归。

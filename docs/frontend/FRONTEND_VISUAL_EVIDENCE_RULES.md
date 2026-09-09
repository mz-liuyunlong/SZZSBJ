# Frontend Visual Evidence Rules

## Required Evidence

- 视觉验收必须说明环境、route、viewport、前置状态、步骤和结果。
- 至少验证任务指定桌面与窄屏；检查 window/body 溢出、内部滚动、Modal/Drawer、焦点和可达操作。
- 截图只证明可见状态，不能替代 Vitest、E2E、console、network 或权限测试。
- Evidence 不得包含真实账号、secret、敏感数据或生产 URL。
- 只展示真实运行结果；设计稿、mockup 和实现截图必须明确区分。
- 发现 console error、network error、截断、重叠或无障碍缺陷必须报告，不裁剪掩盖。

Ready 页面按项目 E2E 标准提供浏览器级证据；no-api 页面不得调用真实 API。

# 使用 Context7 查询第三方库文档提示词

当任务涉及第三方库、框架、SDK、CLI、测试工具或依赖升级时，把下面这段放入 Codex / AI 任务中：

```text
本任务涉及第三方库用法。请先使用 Context7 或官方文档核对当前版本文档，再编写代码。

必须遵守：
1. 不要凭训练记忆猜 API。
2. 不要引入未批准的新依赖。
3. 不要把 Context7 加入 frontend/backend 业务依赖。
4. 不要把 Context7 加入 CI、Dockerfile、postinstall。
5. 不要提交 Context7 API Key、MCP Token、OAuth 信息。
6. 如果 Context7 文档和项目规则冲突，以项目规则为准，并停止询问。

完成报告中必须写：
- 查询的库
- 查询的版本
- 查询的问题
- 采用的结论
- 是否仍有不确定点
```

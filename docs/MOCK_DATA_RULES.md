# Mock 数据规则

## 文件用途

本文件用于约束新项目开发阶段 Mock 数据的使用方式。

## 规则

1. Mock 数据只能用于开发阶段。
2. Mock 数据必须集中放置。
3. Mock 数据不能散落在页面组件中。
4. Mock 数据必须有明显命名。
5. Mock 数据不能伪装成真实接口数据。
6. 上线前必须可以切换到真实 API。

## 推荐目录

```text
frontend/src/mocks/
backend/app/mocks/
```

禁止在页面里直接写大量假数据。如必须临时使用 mock，必须标记 TODO 并说明替换真实 API 的路径。

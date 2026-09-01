# API 文档与 API 文档页面标准

## 1. API 文档页面位置

```text
🗄 数据中心 → API文档
```

权限点：

```text
data_center.api_docs.view
```

API 文档页面不是普通用户入口，只给开发、管理员、维护人员查看。

## 2. 后端接口完成标准

每个后端接口完成时必须同步交付：

```text
FastAPI route
Pydantic request schema
Pydantic response schema
response_model
统一返回格式
OpenAPI 可见
openapi_extra 业务元数据
Markdown API 文档
API 文档页面可见
测试
```

没有 API 文档 = 接口未完成。

## 3. 文档内容

每个接口文档必须包含：

```text
接口名称
URL
Method
页面位置
所需 permissionKey
数据权限
请求参数
返回字段
分页
排序
错误码
数据来源
来源表
是否只读
是否写审计
是否高危
示例请求
示例返回
```

## 4. API 文档页面第一版功能

```text
读取 /openapi.json
显示接口列表
按模块 / 方法 / 路径搜索
点开接口显示请求参数、返回字段、错误码
显示 source / sourceTables / readonly / highRisk / permission
提供 /docs 和 /redoc 跳转
```

第一版不要做：

```text
在线调试真实接口
在线修改接口文档
普通员工可见
高危接口一键调用
```

## 5. 安全边界

API 文档不得展示：

```text
真实 Token
数据库连接串
完整 Webhook
内部密钥
密码
```

生产环境不允许通过 API 文档页面直接执行高危接口。

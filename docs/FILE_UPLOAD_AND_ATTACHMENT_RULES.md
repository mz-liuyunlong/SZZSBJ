# File Upload and Attachment Rules

## Required Rules

- 每种文件先定义业务用途、允许格式/MIME、大小、数量、owner、敏感级别、保留和删除策略。
- 不能只信扩展名或客户端 MIME；后端验证类型、大小、结构和安全扫描结果。
- 文件名、路径和 object key 必须由服务端安全生成；禁止路径穿越和公开永久 URL。
- 上传使用受控暂存/RAW 边界，校验成功后才发布；失败和 quarantine 可追踪。
- 下载执行 permission/data scope/field/export 检查并记录 audit。
- 文件不得包含 secret；敏感文件加密、限时访问、最小权限并有删除传播。
- 解析器限制资源、行数、压缩比和公式/宏风险。

真实对象存储、病毒扫描和文件业务流程需要独立 PRP，不由本规则自动批准。

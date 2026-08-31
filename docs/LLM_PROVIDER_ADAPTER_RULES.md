# LLM Provider Adapter 规则

## 文件用途

本文件用于约束系统内 AI 模型调用方式，避免业务代码直接散落调用 OpenAI SDK。

## 总原则

1. 业务 Service 不直接调用 OpenAI SDK。
2. 所有模型调用必须经过统一 LLM Provider Adapter。
3. 默认实现使用 OpenAI Python SDK。
4. Prompt 必须有版本号。
5. 输入输出必须有 Schema。
6. 模型调用失败必须有明确错误处理。
7. AI 输出默认是建议，不自动执行生产操作。

## 推荐目录

```text
backend/app/integrations/llm/
├── base.py
├── openai_provider.py
├── schemas.py
└── prompt_registry.py
```

## 需要记录的信息

- model
- prompt_version
- input_summary
- output_summary
- error_code
- latency_ms
- token_usage，如可用
- created_by
- created_at

敏感输入不得完整写入日志。

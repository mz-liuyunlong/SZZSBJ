# 项目目录结构规范

## 推荐根目录结构

```text
project-root/
├── frontend/                 # 新前端
├── backend/                  # 新后端
├── old-system/               # 旧系统只读参考
├── docs/                     # 项目文档
├── skills/                   # 项目级 AI Skills
├── .github/                  # GitHub 协作规则
├── .cursor/                  # Cursor 规则入口
├── AGENTS.md                 # AI 总规则
├── AI_START_HERE.md          # AI 通用启动入口
└── README_AI_RULES.md        # 人看的规则说明
```

## 新旧系统隔离

新系统代码不得直接引用 `old-system/` 中任何文件。

禁止：

```ts
import x from '../../old-system/...'
```

禁止：

```python
from old_system.xxx import y
```

## 文档输出位置

旧系统分析结果统一写入：`docs/old-system-analysis/`。  
架构决策写入：`docs/adr/`。  
任务交接写入：`docs/handoffs/`。  
页面需求写入：`docs/page-specs/`。  
API 契约写入：`docs/api-contracts/`。

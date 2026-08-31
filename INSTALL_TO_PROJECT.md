# 安装到项目中的方式

## 1. 解压位置

把本规则包解压到你的项目根目录，要求与 `.git/` 同级。

正确示例：

```text
project-root/
├── .git/
├── AGENTS.md
├── docs/
├── .github/
├── .cursor/
├── skills/
├── frontend/
├── backend/
└── old-system/
```

不要放进 `.git/` 目录。

## 2. CODEOWNERS

`.github/CODEOWNERS` 已默认使用：

```text
@mz-liuyunlong
```

如 GitHub 用户名变化，请自行替换。

## 3. old-system 默认建议

初期建议不要把旧系统真实代码提交到远程仓库。可将旧系统代码放在本地 `old-system/` 中，并在 `.gitignore` 中使用推荐规则：

```gitignore
old-system/*
!old-system/README.md
```

旧系统分析结果写入：

```text
docs/old-system-analysis/
```

## 4. 不建议直接覆盖已有文件

如果你的项目已经有 `.github/`、`.cursor/`、`docs/` 或其他文件，请先对比内容后合并，不要盲目覆盖。

## Ponytail 项目兼容规则

v1.4.2 起，规则包已经包含项目级 Ponytail 兼容规则：

```text
docs/PONYTAIL_COMPATIBILITY_RULES.md
docs/tools/PONYTAIL_INSTALL_GUIDE.md
```

请将它们一并提交到 GitHub。这样其他人拉取项目后，即使没有安装官方 Ponytail 插件、没有阅读安装说明、没有主动提醒 AI，AI 也会通过项目规则默认执行 Ponytail 简化原则。

不要把官方 Ponytail 插件安装写进 `npm install`、`postinstall`、CI、Vercel 或 Docker 构建流程。官方插件属于每个开发者自己的 AI 工具配置。


---

## 新开发者 AI 工具首次配置

v1.4.4 起，项目提供 AI 工具首次配置脚本：

```bash
bash scripts/check-ai-tools.sh
bash scripts/setup-ai-tools.sh
```

开发者拉取项目后，应让 AI 先读取：

```text
AI_ONBOARDING.md
docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md
```

然后由 AI 协助执行安装。

注意：不要把官方 Ponytail 插件安装写入 `npm install` 或 `postinstall`。官方插件是开发者本机 AI 工具配置，hooks 必须由用户审查并信任。

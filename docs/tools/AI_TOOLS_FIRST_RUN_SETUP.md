# AI 工具首次配置规则

## 文件用途

本文件用于规定：开发者第一次拉取本项目后，AI 必须主动帮助完成 AI 编程工具配置，尤其是官方 Ponytail 插件安装。

本项目默认假设开发者会让 AI 帮忙执行配置，而不是自己阅读所有安装说明。

---

## 核心结论

Ponytail 在本项目中分为两层：

| 层级 | 内容 | 是否必须 | 作用 |
|---|---|---:|---|
| 官方插件层 | 官方 Ponytail plugin / extension / skills / hooks | Codex、Claude Code 等支持时应安装 | 获得官方 hooks 和工具级自动注入能力 |
| 项目规则层 | `docs/PONYTAIL_COMPATIBILITY_RULES.md` | 必须 | 任何 AI 都默认执行 Ponytail 最小正确实现原则 |

没有官方 hooks，就不是完整官方 Ponytail。  
所以支持官方插件的 AI 工具，应优先安装官方 Ponytail 插件。

但官方插件安装失败或当前工具不支持插件时，不允许跳过 Ponytail 原则，必须使用项目内置规则兜底。

---

## AI 首次接手项目必须执行

AI 第一次接手本项目时，必须先做 AI 工具配置检查，而不是直接开始业务开发。

必须按顺序执行：

```text
读取 AI_ONBOARDING.md
↓
读取 AI_DAILY_RULES.md
↓
读取 AGENTS.md
↓
读取 docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md
↓
检查当前 AI 工具类型
↓
检查是否可以安装官方 Ponytail 插件
↓
支持则协助安装
↓
需要 hooks 信任时停下来让用户确认
↓
进入项目规则读取与 Skill 自发现流程
```

---

## 推荐执行脚本

项目提供脚本：

```bash
bash scripts/setup-ai-tools.sh
```

该脚本用于检测并安装当前机器上可用的 AI 工具插件。

AI 有终端执行能力时，应在用户确认后执行：

```bash
bash scripts/setup-ai-tools.sh
```

或仅检查：

```bash
bash scripts/check-ai-tools.sh
```

---

## Codex 安装要求

如果检测到 `codex` 命令，AI 应帮助执行：

```bash
codex plugin marketplace add DietrichGebert/ponytail
codex plugin add ponytail@ponytail
```

安装后，AI 必须提醒用户进入 Codex：

```bash
codex
```

然后在 Codex 内输入：

```text
/hooks
```

用户必须亲自审查并信任 Ponytail hooks。

AI 不得自动替用户信任 hooks。

---

## Claude Code 安装要求

如果开发者使用 Claude Code，AI 应提示开发者在 Claude Code 里分别发送：

```text
/plugin marketplace add DietrichGebert/ponytail
```

然后发送：

```text
/plugin install ponytail@ponytail
```

如 Claude Code 要求信任 hooks，必须由用户确认。

---

## GitHub Copilot CLI 安装要求

如果检测到 `copilot` 命令，AI 可以帮助执行：

```bash
copilot plugin marketplace add DietrichGebert/ponytail
copilot plugin install ponytail@ponytail
```

如果命令失败，不得阻断项目开发，改用项目内置 Ponytail 规则。

---

## Gemini CLI 安装要求

如果检测到 `gemini` 命令，AI 可以帮助执行：

```bash
gemini extensions install https://github.com/DietrichGebert/ponytail
```

如果命令失败，不得阻断项目开发，改用项目内置 Ponytail 规则。

---

## 不允许的自动安装方式

AI 不允许把 Ponytail 官方插件安装写入：

1. `npm install`
2. `npm postinstall`
3. Vercel build
4. Docker build
5. CI workflow
6. 后端启动脚本
7. 前端启动脚本

原因：官方 Ponytail 插件属于开发者本机 AI 工具配置，不是项目运行依赖。

---

## 安装失败时的处理

如果官方 Ponytail 插件无法安装，AI 必须输出：

```text
当前环境未成功安装官方 Ponytail 插件。
本次将使用项目内置 Ponytail 默认规则：docs/PONYTAIL_COMPATIBILITY_RULES.md。
```

然后继续遵守项目规则，不得因为插件失败而跳过最小正确实现检查。

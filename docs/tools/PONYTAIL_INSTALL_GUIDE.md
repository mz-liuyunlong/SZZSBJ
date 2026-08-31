# Ponytail 官方插件安装指南

## 文件用途

本文件用于团队安装官方 Ponytail 插件。

注意：本项目已经内置 `docs/PONYTAIL_COMPATIBILITY_RULES.md`，所以 Ponytail 最小正确实现原则在项目内默认开启。

但没有官方 hooks，就不是完整官方 Ponytail。因此，支持官方插件的 AI 工具应优先安装官方 Ponytail 插件。

---

## 一键辅助脚本

第一次拉取项目后，建议让 AI 执行：

```bash
bash scripts/setup-ai-tools.sh
```

只检查不安装：

```bash
bash scripts/check-ai-tools.sh
```

脚本会检测当前机器是否有 Codex、GitHub Copilot CLI、Gemini CLI，并在用户确认后执行对应安装命令。

脚本不会替用户信任 hooks。

---

## Codex

```bash
codex plugin marketplace add DietrichGebert/ponytail
codex plugin add ponytail@ponytail
```

安装后进入 Codex：

```bash
codex
```

然后输入：

```text
/hooks
```

审查并信任 Ponytail hooks。

---

## Claude Code

在 Claude Code 中分别发送：

```text
/plugin marketplace add DietrichGebert/ponytail
```

然后发送：

```text
/plugin install ponytail@ponytail
```

如果 Claude Code 要求审查 hooks，必须由用户确认。

---

## GitHub Copilot CLI

```bash
copilot plugin marketplace add DietrichGebert/ponytail
copilot plugin install ponytail@ponytail
```

---

## Gemini CLI

```bash
gemini extensions install https://github.com/DietrichGebert/ponytail
```

---

## 不要放进 npm install

不要把官方 Ponytail 安装写入：

```json
{
  "scripts": {
    "postinstall": "codex plugin add ponytail@ponytail"
  }
}
```

原因：

1. AI 工具插件是开发者本机配置，不是项目运行依赖。
2. 有些开发者不用 Codex。
3. CI、Vercel、Docker 里可能失败。
4. hooks 必须由用户手动审查并信任。
5. 不应在 `npm install` 时偷偷修改开发者全局 AI 环境。

---

## 安装失败怎么办

安装失败不阻断项目开发。

AI 必须继续按以下文件执行 Ponytail 默认规则：

```text
docs/PONYTAIL_COMPATIBILITY_RULES.md
```

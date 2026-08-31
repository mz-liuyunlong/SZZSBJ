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

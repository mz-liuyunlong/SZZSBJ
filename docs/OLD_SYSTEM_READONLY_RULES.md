# old-system 只读参考规则

## 文件用途

本文件用于约束 AI 如何读取和分析 `old-system/` 目录。

`old-system/` 是旧系统代码归档目录，只作为新系统重建时的业务参考资料。AI 不允许修改 `old-system/`。

## old-system 的定位

`old-system/` 用于帮助 AI 理解：旧页面、旧 API、旧数据库表、旧定时任务、旧导入导出、旧业务计算逻辑、旧第三方接口封装，以及哪些旧设计不应延续。

`old-system/` 不是新系统代码目录。

## 允许操作

AI 可以对 `old-system/` 执行只读操作，例如：

```bash
find old-system -type f
grep -R "keyword" old-system
cat old-system/path/to/file
sed -n '1,160p' old-system/path/to/file
```

AI 可以输出：功能清单、页面清单、API 清单、数据表清单、字段说明、业务规则说明、新旧功能映射、新系统重建建议。

## 禁止操作

AI 禁止对 `old-system/` 执行：

```bash
git add old-system
rm -rf old-system
mv old-system
cp -r old-system new-system
npm install
npm run build
npm run dev
python script.py
node script.js
alembic upgrade head
```

除非项目负责人明确授权，并且确认不会修改旧代码、不会写入生产数据库、不会触发旧系统任务。

## 禁止修改 old-system

AI 不允许修改：

```text
old-system/**
```

如需记录旧系统分析结果，应写入：

```text
docs/old-system-analysis/
```

而不是写回 `old-system/`。

## 禁止复制旧代码

正确流程：

```text
读取 old-system
↓
提炼业务规则
↓
输出分析文档
↓
设计新系统模块
↓
用户确认
↓
在新系统目录重新实现
```

禁止流程：

```text
读取 old-system
↓
复制旧代码
↓
改几个路径
↓
塞进新系统
```

## 敏感信息规则

如果 `old-system/` 中存在密钥、Token、数据库密码、服务器配置，AI 必须不输出完整密钥、不复制到新系统、不提交到 GitHub，并提醒用户存在敏感信息风险。

## 旧系统分析输出模板

| 旧系统位置 | 旧功能 | 数据来源 | 新系统模块 | 是否重建 | 风险 |
|---|---|---|---|---|---|
| `old-system/...` |  |  |  | 是/否/待确认 |  |

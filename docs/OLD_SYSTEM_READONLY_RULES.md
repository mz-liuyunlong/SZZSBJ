# old-system 只读参考规则

## 文件用途

本文件用于约束 AI 如何读取和分析 `old-system/` 目录。

`old-system/` 是旧系统代码归档目录，只作为新系统重建时的业务参考资料。AI 不允许修改 `old-system/`。

## old-system 的定位

`old-system/` 用于帮助 AI 理解：

1. 旧系统有哪些页面。
2. 旧系统有哪些 API。
3. 旧系统有哪些数据库表。
4. 旧系统有哪些定时任务。
5. 旧系统有哪些导入导出。
6. 旧系统有哪些业务计算逻辑。
7. 旧系统哪些功能需要在新系统重建。
8. 旧系统哪些设计不应延续。

`old-system/` 不是新系统代码目录。

## 允许操作

AI 可以对 `old-system/` 执行只读操作，例如：

```bash
find old-system -type f
grep -R "keyword" old-system
cat old-system/path/to/file
sed -n '1,160p' old-system/path/to/file
```

AI 可以输出：

- 功能清单
- 页面清单
- API 清单
- 数据表清单
- 字段说明
- 业务规则说明
- 新旧功能映射
- 新系统重建建议

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

包括：

- 代码文件
- 配置文件
- package.json
- requirements.txt
- 数据库脚本
- 定时任务
- README
- 环境变量模板
- 部署配置

如需记录旧系统分析结果，应写入：

```text
docs/old-system-analysis/
```

而不是写回 `old-system/`。

## 禁止复制旧代码

AI 不允许把旧代码原样复制到新系统。

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

如果 `old-system/` 中存在密钥、Token、数据库密码、服务器配置，AI 必须：

1. 不输出完整密钥。
2. 不复制到新系统。
3. 不提交到 GitHub。
4. 提醒用户存在敏感信息风险。
5. 建议只保留 `.env.example` 或脱敏样例。

## 旧系统分析输出模板

| 旧系统位置 | 旧功能 | 数据来源 | 新系统模块 | 是否重建 | 风险 |
|---|---|---|---|---|---|
| `old-system/...` |  |  |  | 是/否/待确认 |  |

## AI 回答要求

涉及 `old-system/` 时，AI 必须明确说明：

1. 本次只读了哪些旧系统文件。
2. 没有修改 `old-system/`。
3. 提炼出的业务规则是什么。
4. 哪些规则可以在新系统重新实现。
5. 哪些旧代码设计不建议延续。
6. 下一步是否需要用户确认。

#!/usr/bin/env bash
# check_layer_definition_unique.sh
# 用途：校验「分层链路 / AI 边界」的定义在全仓只存在于唯一权威位置。
# 背景：2026-08-14 实证曾并存三套互相冲突的定义（PROJECT_CONTEXT / DATABASE_MAP / README），
#       其中 DATABASE_MAP 那套还额外授权了 AI 写 BIZ 层，与六条原则第 4 条冲突。
#       任何被复述两遍的事实都必然漂移，因此改为单一来源 + 机器校验。
# 设计说明（2026-08-14 修订，勿退回旧版）：
#       第 3 节最初用负向字符串匹配禁令措辞，两次误报——先误伤「受限账号读 DIM/FACT/BIZ」，
#       后误伤「记述该授权已撤销」的说明文字与 TASK_CHANGE_LOG 归档记录。
#       禁令的字面匹配必然命中引用该禁令的文本，故改为正向断言为主、负向扫描收窄。
#       TASK_CHANGE_LOG.md 是只增不改的历史日志，按定义长期引用旧措辞，整体排除。
# 用法：bash scripts/check_layer_definition_unique.sh
# 退出码：0=通过；1=发现问题
set -uo pipefail
cd "$(dirname "$0")/.."

AUTH_FILE="context/PROJECT_CONTEXT.md"
AUTH_HEAD="## 数据分层与 AI 边界（唯一权威定义）"
MAP_FILE="context/DATABASE_MAP.md"
FAIL=0

echo "== 1. 权威定义是否存在 =="
if grep -qF "$AUTH_HEAD" "$AUTH_FILE"; then
  echo "OK: $AUTH_FILE 存在权威节"
else
  echo "FAIL: 未在 $AUTH_FILE 找到权威节标题：$AUTH_HEAD"
  FAIL=1
fi

# 判据：同一行同时出现 数据源 + RAW + (DIM 或 AI层) = 在复述全局分层定义。
# 只描述某条具体管道的（如 API->RAW->FACT）不含「数据源」，不会误报。
echo
echo "== 2. 其他文件是否复述全局分层定义 =="
HITS=$(grep -rn --include=*.md -E '数据源.*RAW.*(DIM|AI层)' . 2>/dev/null \
  | grep -v '^\./context/_bak_' \
  | grep -v '^\./context/_prod_pull_' \
  | grep -v '^\./_to_delete/' \
  | grep -v '^\./legacy_' \
  | grep -v '^\./node_modules/' \
  | grep -v "^\./$AUTH_FILE:" \
  | grep -v '^\./context/TASK_CHANGE_LOG\.md:' || true)
if [ -n "$HITS" ]; then
  echo "FAIL: 以下位置复述了全局分层定义，请改为引用"
  echo "      引用写法：见 context/PROJECT_CONTEXT.md「数据分层与 AI 边界」"
  echo "$HITS"
  FAIL=1
else
  echo "OK: 未发现复述"
fi

echo
echo "== 3a. 正向断言：BIZ 层标题已声明 AI 不写本层 =="
if grep -qF '### BIZ层（确定性计算 + 人工定稿层；AI 不写本层）' "$MAP_FILE"; then
  echo "OK: BIZ 层标题正确"
else
  echo "FAIL: $MAP_FILE 缺少正确的 BIZ 层标题"
  echo "      期望：### BIZ层（确定性计算 + 人工定稿层；AI 不写本层）"
  FAIL=1
fi

echo
echo "== 3b. 正向断言：旧 BIZ 标题不得残留 =="
if grep -qF '### BIZ层（人工/AI 定稿层）' "$MAP_FILE"; then
  echo "FAIL: $MAP_FILE 仍残留旧标题「### BIZ层（人工/AI 定稿层）」"
  FAIL=1
else
  echo "OK: 旧标题已清除"
fi

echo
echo "== 3c. 负向扫描：规范性文档中是否有现行的 AI 写 BIZ 授权 =="
# 排除历史日志与叙述性行（撤销/曾/历史/原有/归属修正/误判/设计说明）
GRANT=$(grep -rn --include=*.md -E 'AI (只写|可写|得写)[^。]{0,20}BIZ|AI 写 BIZ 层|人工/AI 定稿层' . 2>/dev/null \
  | grep -v '^\./context/_bak_' \
  | grep -v '^\./context/_prod_pull_' \
  | grep -v '^\./_to_delete/' \
  | grep -v '^\./legacy_' \
  | grep -v '^\./node_modules/' \
  | grep -v '^\./context/TASK_CHANGE_LOG\.md:' \
  | grep -vE '撤销|曾|历史|原有|归属修正|误判|设计说明' || true)
if [ -n "$GRANT" ]; then
  echo "FAIL: 以下位置存在现行的 AI 写 BIZ 授权，与六条原则第 4 条冲突"
  echo "$GRANT"
  FAIL=1
else
  echo "OK: 未发现现行授权"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "ALL PASS: 分层定义唯一，BIZ 层已声明 AI 不写，无现行越权授权"
  exit 0
fi
echo "CHECK FAILED: 见上方 FAIL 明细"
exit 1

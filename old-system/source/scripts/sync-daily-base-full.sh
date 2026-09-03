#!/usr/bin/env bash
set -euo pipefail

echo "执行当日数据同步..."
npm run sync:daily-base -- "$@"

CONFIRM_WRITE=0
for arg in "$@"; do
  if [ "$arg" = "--confirm-write" ]; then
    CONFIRM_WRITE=1
  fi
done

if [ "$CONFIRM_WRITE" = "1" ]; then
  echo "检测到 --confirm-write，开始补写 H/I/M 公式..."
  npm run sync:formulas
  echo "当日数据同步 + 公式补写完成。"
else
  echo "未检测到 --confirm-write，本次只执行 dry-run，不补写公式。"
fi

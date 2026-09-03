#!/usr/bin/env bash
# code_sync_diff.sh —— 本地比对（不调ssh）：读已取回的线上md5清单，与Mac本地逐文件比对
# 前置：需先用一条ssh命令把线上md5取到 /tmp/prod_md5.txt 与 /tmp/prod_fe_md5.txt
REPO="/Users/chen/Documents/New project"
exec > /tmp/code_sync_diff.log 2>&1
echo "code_sync_diff $(date '+%F %T')"
cd "$REPO" || { echo "找不到仓库 $REPO"; exit 1; }

for f in /tmp/prod_md5.txt /tmp/prod_fe_md5.txt; do
  if [ ! -s "$f" ]; then echo "❌ 缺少 $f（请先执行步骤1的ssh取数命令）"; exit 1; fi
done

md5of(){ md5 -q "$1" 2>/dev/null || md5sum "$1" 2>/dev/null | awk '{print $1}'; }

# 本地清单（排除 macOS ._ 元数据垃圾）
: > /tmp/local_md5.txt
while IFS= read -r p; do
  [ -f "$p" ] && echo "$(md5of "$p") ${p}" >> /tmp/local_md5.txt
done < <(find src -maxdepth 1 -name '*.ts' -not -name '._*' | sort)
: > /tmp/local_fe_md5.txt
while IFS= read -r p; do
  [ -f "$p" ] && echo "$(md5of "$p") ${p}" >> /tmp/local_fe_md5.txt
done < <(find admin-frontend/src -type f \( -name '*.tsx' -o -name '*.ts' \) -not -name '._*' | sort)

# 线上清单规整为 "md5 相对路径"
sed -e 's#/opt/lingxing-auto/##' /tmp/prod_md5.txt    | awk '{print $1" "$2}' | sort -k2 > /tmp/_p1.txt
sed -e 's#/opt/lingxing-auto/##' /tmp/prod_fe_md5.txt | awk '{print $1" "$2}' | sort -k2 > /tmp/_p2.txt
sort -k2 /tmp/local_md5.txt    > /tmp/_l1.txt
sort -k2 /tmp/local_fe_md5.txt > /tmp/_l2.txt

cmp_set(){
  local L="$1" P="$2" NAME="$3"
  echo ""
  echo "===== $NAME ====="
  echo "本地文件数: $(wc -l < "$L")   线上文件数: $(wc -l < "$P")"
  echo ""
  echo "--- ⚠️ 内容不一致（需同步）---"
  join -j 2 -o 0,1.1,2.1 "$L" "$P" 2>/dev/null | awk '$2!=$3 {print "  ⚠️ "$1"\n      本地:"$2"\n      线上:"$3}'
  echo "  (空=全部一致)"
  echo ""
  echo "--- 📤 仅本地有（未部署到线上）---"
  join -v1 -j 2 "$L" "$P" 2>/dev/null | awk '{print "  📤 "$1}'
  echo "  (空=无)"
  echo ""
  echo "--- 📥 仅线上有（本地缺失，可能线上被直接改过）---"
  join -v2 -j 2 "$L" "$P" 2>/dev/null | awk '{print "  📥 "$1}'
  echo "  (空=无)"
}

cmp_set /tmp/_l1.txt /tmp/_p1.txt "后端 src/*.ts"
cmp_set /tmp/_l2.txt /tmp/_p2.txt "前端 admin-frontend/src"

echo ""
echo "===== 今晚涉及的关键文件专项 ====="
for f in src/checkSemNamingCompliance.ts src/checkSemNamingDeduction.ts src/checkSemImport.ts src/aiFinanceRoutes.ts src/syncWalmartBillDaily.ts; do
  L=$(md5of "$f")
  P=$(awk -v k="$f" '$2==k{print $1}' /tmp/_p1.txt)
  if [ -z "$P" ]; then S="❌线上不存在"; elif [ "$L" = "$P" ]; then S="✅一致"; else S="⚠️不一致"; fi
  echo "  $S  $f"
  echo "        本地=$L"
  echo "        线上=${P:-（未取到）}"
done

echo ""
echo "===== macOS ._ 元数据垃圾文件（不应存在于仓库）====="
find src admin-frontend/src -name '._*' 2>/dev/null | sed 's/^/  🗑 /'
echo "  (空=干净)"
echo "---- done ----"

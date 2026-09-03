#!/usr/bin/env bash
# code_sync_check.sh —— Mac仓库 与 生产机 /opt/lingxing-auto 代码一致性核对（只读，零写入）
# 在【Mac】上运行：本地算md5 → ssh到prod算md5 → 逐文件比对，列出 差异/仅本地/仅线上
REPO="/Users/chen/Documents/New project"
OUT="/tmp/code_sync_check.log"
exec > "$OUT" 2>&1
echo "code_sync_check $(date '+%F %T')"
cd "$REPO" || { echo "找不到仓库 $REPO"; exit 1; }

echo "===== 1. 本地 src/*.ts 文件数 ====="
ls src/*.ts 2>/dev/null | wc -l

echo ""
echo "===== 2. 逐文件比对（src 目录 .ts）====="
# 本地 md5
find src -maxdepth 1 -name '*.ts' -type f -exec md5 -r {} \; 2>/dev/null | sort -k2 > /tmp/_local_md5.txt \
  || find src -maxdepth 1 -name '*.ts' -type f -exec md5sum {} \; 2>/dev/null | awk '{print $1" "$2}' | sort -k2 > /tmp/_local_md5.txt
# 线上 md5
ssh company-ai 'cd /opt/lingxing-auto && find src -maxdepth 1 -name "*.ts" -type f -exec md5sum {} \; | awk "{print \$1\" \"\$2}" | sort -k2' > /tmp/_prod_md5.txt 2>/dev/null

echo "本地文件数: $(wc -l < /tmp/_local_md5.txt)   线上文件数: $(wc -l < /tmp/_prod_md5.txt)"
echo ""
echo "--- 2.1 内容不一致的文件（需要同步！）---"
join -j 2 -o 0,1.1,2.1 /tmp/_local_md5.txt /tmp/_prod_md5.txt 2>/dev/null \
  | awk '$2!=$3 {print "  ⚠️ "$1"\n      本地:"$2"\n      线上:"$3}'
echo "(以上为空=全部一致)"

echo ""
echo "--- 2.2 仅本地有（未部署到线上）---"
join -v1 -j 2 /tmp/_local_md5.txt /tmp/_prod_md5.txt 2>/dev/null | awk '{print "  📤 "$1}'
echo "(以上为空=无未部署文件)"

echo ""
echo "--- 2.3 仅线上有（本地缺失，可能是线上直接改的！）---"
join -v2 -j 2 /tmp/_local_md5.txt /tmp/_prod_md5.txt 2>/dev/null | awk '{print "  📥 "$1}'
echo "(以上为空=无线上独有文件)"

echo ""
echo "===== 3. 前端 admin-frontend/src 比对 ====="
find admin-frontend/src -name '*.tsx' -o -name '*.ts' 2>/dev/null | head -1 >/dev/null && {
  (find admin-frontend/src -type f \( -name '*.tsx' -o -name '*.ts' \) -exec md5 -r {} \; 2>/dev/null \
    || find admin-frontend/src -type f \( -name '*.tsx' -o -name '*.ts' \) -exec md5sum {} \; 2>/dev/null | awk '{print $1" "$2}') | sort -k2 > /tmp/_local_fe.txt
  ssh company-ai 'cd /opt/lingxing-auto && find admin-frontend/src -type f \( -name "*.tsx" -o -name "*.ts" \) -exec md5sum {} \; | awk "{print \$1\" \"\$2}" | sort -k2' > /tmp/_prod_fe.txt 2>/dev/null
  echo "本地前端文件数: $(wc -l < /tmp/_local_fe.txt)   线上: $(wc -l < /tmp/_prod_fe.txt)"
  echo "--- 3.1 前端内容不一致 ---"
  join -j 2 -o 0,1.1,2.1 /tmp/_local_fe.txt /tmp/_prod_fe.txt 2>/dev/null | awk '$2!=$3 {print "  ⚠️ "$1}'
  echo "--- 3.2 仅本地有 ---"
  join -v1 -j 2 /tmp/_local_fe.txt /tmp/_prod_fe.txt 2>/dev/null | awk '{print "  📤 "$1}'
  echo "--- 3.3 仅线上有 ---"
  join -v2 -j 2 /tmp/_local_fe.txt /tmp/_prod_fe.txt 2>/dev/null | awk '{print "  📥 "$1}'
}

echo ""
echo "===== 4. 线上服务与构建状态 ====="
ssh company-ai 'echo "--- git状态(若为git仓库) ---"; cd /opt/lingxing-auto && (git status --short 2>/dev/null | head -20 || echo "(非git仓库)"); echo "--- 服务状态 ---"; systemctl is-active lingxing-admin 2>/dev/null; echo "--- 最近修改的src文件(近3天) ---"; find src -maxdepth 1 -name "*.ts" -mtime -3 -printf "%TY-%Tm-%Td %TH:%TM  %p\n" 2>/dev/null | sort -r | head -15'

echo ""
echo "===== 5. 今晚涉及的关键文件专项核对 ====="
for f in src/checkSemNamingCompliance.ts src/checkSemNamingDeduction.ts src/checkSemImport.ts src/aiFinanceRoutes.ts src/syncWalmartBillDaily.ts; do
  L=$( (md5 -q "$f" 2>/dev/null || md5sum "$f" 2>/dev/null | awk '{print $1}') )
  P=$(ssh company-ai "md5sum /opt/lingxing-auto/$f 2>/dev/null | awk '{print \$1}'")
  if [ -z "$P" ]; then S="❌线上不存在"; elif [ "$L" = "$P" ]; then S="✅一致"; else S="⚠️不一致"; fi
  echo "  $S  $f   本地=$L  线上=$P"
done
echo "---- done ----"

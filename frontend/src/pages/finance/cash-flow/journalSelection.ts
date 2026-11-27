/** 日记账勾选列配置（批量操作用）；单独放一个文件，组件文件只导出组件。 */
import { Table } from "antd";
import type { TableRowSelection } from "antd/es/table/interface";
import type { Key } from "react";
import type { CashCategory, CashLine } from "@/pages/finance/localFinData";
import { isPartRow } from "@/pages/finance/cash-flow/journalParts";

/** 勾选列：固定在最左边（日期列前面），表头勾选框 = 本页全选，下拉里有「全选所有（当前筛选的全部页）/ 反选当页 / 清空所有」。 */
export function journalRowSelection(keys: string[], onChange: (keys: string[]) => void): TableRowSelection<CashLine> {
  return {
    fixed: "left",
    columnWidth: 48,
    selectedRowKeys: keys,
    preserveSelectedRowKeys: true,
    onChange: (next: Key[]) => onChange(next.map(String)),
    selections: [Table.SELECTION_ALL, Table.SELECTION_INVERT, Table.SELECTION_NONE],
    /* 拆分子行不能勾，勾父行也不连带子行 */
    checkStrictly: true,
    getCheckboxProps: (row) => ({ disabled: isPartRow(row) }),
  };
}

/** 类别下拉选项：按大类分组；includeX01 = false 时不列 X01（剔除要用剔除按钮写原因）。 */
export function groupedCatOptions(cats: CashCategory[], includeX01 = false) {
  const groups = new Map<string, { value: string; label: string }[]>();
  for (const cat of cats) {
    if (cat.code === "X01" && !includeX01) continue;
    groups.set(cat.big, [...(groups.get(cat.big) ?? []), { value: cat.code, label: `${cat.code} ${cat.big}·${cat.name}` }]);
  }
  return Array.from(groups, ([big, options]) => ({ label: big, title: big, options }));
}

/** 类别模糊搜索：输入几个字（可以空格隔开）都在「代码 大类·名称」里出现就算；也认按顺序出现的字，如「手费」能找到「手续费」。 */
export function catFilter(input: string, option?: { label?: unknown; value?: unknown }) {
  const text = `${String(option?.label ?? "")} ${String(option?.value ?? "")}`.toLowerCase();
  const words = input.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  if (words.every((word) => text.includes(word))) return true;
  let at = 0;
  for (const char of words.join("")) {
    at = text.indexOf(char, at);
    if (at < 0) return false;
    at += 1;
  }
  return true;
}

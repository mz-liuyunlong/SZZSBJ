/**
 * LxToolbar.tsx — 领星式标准工具条共享件（2026-07-24 自 FeishuRawSalesData 提取，逐字一致）
 * 统一规范：所有列表/台账页的 筛选/刷新/帮助/下载/列配置 工具条一律复用本件的样式与图标，
 *   禁止各页自造。FeishuRawSalesData 内嵌版本保持不动（分叉大文件不整改，同 LxMultiSelect 策略）。
 * 导出：lxTB（filterWrap/filterInput/filterSelect/searchBtn/resetBtn/iconBtn 样式）+ 四个图标组件。
 */
import React from "react";

export const lxTB = {
  filterWrap: { background: "#f8fafc", borderRadius: "8px", border: "1px solid #e5e7eb", padding: "12px 14px", marginBottom: "12px" } as React.CSSProperties,
  filterInput: { padding: "6px 10px", borderRadius: "6px", border: "1px solid #e5e7eb", fontSize: "13px", width: "140px", outline: "none", background: "#fff" } as React.CSSProperties,
  filterSelect: { padding: "6px 10px", borderRadius: "6px", border: "1px solid #e5e7eb", fontSize: "13px", width: "160px", outline: "none", background: "#fff", cursor: "pointer" } as React.CSSProperties,
  searchBtn: { padding: "7px 18px", borderRadius: "6px", border: "none", background: "#6366f1", color: "#fff", cursor: "pointer", fontSize: "13px", fontWeight: 600 } as React.CSSProperties,
  resetBtn: { padding: "7px 14px", borderRadius: "6px", border: "1px solid #e5e7eb", background: "#fff", color: "#6b7280", cursor: "pointer", fontSize: "13px" } as React.CSSProperties,
  iconBtn: { background: "none", border: "none", cursor: "pointer", padding: "5px", borderRadius: "6px", color: "#6b7280", display: "inline-flex", alignItems: "center" } as React.CSSProperties,
};

export const IconRefresh = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
  </svg>
);
export const IconHelp = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" /><line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);
export const IconDownload = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);
export const IconColumns = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

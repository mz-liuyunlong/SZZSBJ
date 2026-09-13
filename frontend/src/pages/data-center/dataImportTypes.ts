export type DataImportStatus = "成功" | "部分失败" | "失败";

export type DataImportQuickRange = "all" | "today" | "yesterday" | "7" | "30";

export interface DataImportTypeOption {
  id: string;
  name: string;
  shortName: string;
  icon: string;
  fields: string[];
}

export interface DataImportRecord {
  id: string;
  uploadedAt: string;
  typeName: string;
  fileName: string;
  status: DataImportStatus;
  totalRows: number;
  successRows: number;
  failedRows: number;
  operator: string;
}

export interface DataImportFilters {
  quickRange: DataImportQuickRange;
  startDate: string;
  endDate: string;
  typeName: string;
  status: "" | DataImportStatus;
  keyword: string;
}

export const createInitialDataImportFilters = (): DataImportFilters => ({
  quickRange: "all",
  startDate: "",
  endDate: "",
  typeName: "",
  status: "",
  keyword: "",
});

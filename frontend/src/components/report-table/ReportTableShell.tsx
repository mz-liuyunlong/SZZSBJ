/** Provides the shared fixed-header, scrollable-body, fixed-footer frame for report tables. */
import type { ReactNode } from "react";
import "./reportTable.css";

interface ReportTableShellProps {
  label: string;
  className?: string;
  children: ReactNode;
}

function ReportTableShell({ label, className, children }: ReportTableShellProps) {
  return (
    <section
      className={["report-table-shell", className].filter(Boolean).join(" ")}
      aria-label={label}
    >
      {children}
    </section>
  );
}

export default ReportTableShell;

/** Renders shared page metadata and content without duplicating MainLayout navigation UI. */
import { createContext, useContext, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { NavigationPage } from "@/config/navigation";
import "@/components/page/PageShell.css";

interface PageShellProps {
  page: NavigationPage;
  description?: ReactNode;
  headerActions?: ReactNode;
  children?: ReactNode;
}

interface PageHeaderOutletValue {
  activePageKey: string;
  target: HTMLElement | null;
}

const PageHeaderOutletContext = createContext<PageHeaderOutletValue | null>(null);

export function PageHeaderOutletProvider({
  activePageKey,
  target,
  children,
}: PageHeaderOutletValue & { children: ReactNode }) {
  return (
    <PageHeaderOutletContext.Provider value={{ activePageKey, target }}>
      {children}
    </PageHeaderOutletContext.Provider>
  );
}

function PageShell({ page, headerActions, children }: PageShellProps) {
  const headerOutlet = useContext(PageHeaderOutletContext);
  const headerOutletTarget = headerOutlet?.activePageKey === page.key
    ? headerOutlet.target
    : null;

  const pageActions = headerActions ? (
    <div className="page-shell__header-actions">
      {headerActions}
    </div>
  ) : null;

  return (
    <section className="page-shell" aria-label={page.title}>
      {!headerOutlet && pageActions}
      <div className="page-shell__content">{children}</div>
      {headerOutletTarget && createPortal(pageActions, headerOutletTarget)}
    </section>
  );
}

export default PageShell;

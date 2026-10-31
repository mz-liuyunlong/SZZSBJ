/** Routes each WFS sidebar page to its preview screen. */
import type { NavigationPage } from "@/config/navigation";
import PendingPackingPage from "./PendingPackingPage";
import ShipmentBoardPage from "./ShipmentBoardPage";
import ExceptionCenterPage from "./ExceptionCenterPage";
import WfsStoreSettingsPage from "./WfsStoreSettingsPage";

export default function WfsFrontendPage({ page, scope, permissions }: { page: NavigationPage; scope?: string; permissions?: string[] }) {
  switch (page.key) {
    case "pmc_wfs_pending_packing":
      return <PendingPackingPage page={page} scope={scope} permissions={permissions} />;
    case "pmc_wfs_board":
      return <ShipmentBoardPage page={page} scope={scope} />;
    case "pmc_wfs_exceptions":
      return <ExceptionCenterPage page={page} scope={scope} />;
    case "pmc_wfs_settings":
      return <WfsStoreSettingsPage page={page} canManage={!permissions || permissions.includes("*") || permissions.includes("action:pmc:wfs-settings:manage")} />;
    default:
      return null;
  }
}

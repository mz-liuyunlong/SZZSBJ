/** Routes each WFS sidebar page to its preview screen. */
import type { NavigationPage } from "@/config/navigation";
import PendingPackingPage from "./PendingPackingPage";
import ShipmentBoardPage from "./ShipmentBoardPage";
import ExceptionCenterPage from "./ExceptionCenterPage";
import { WfsSettingsPage } from "./WfsSupportPages";

export default function WfsFrontendPage({ page, scope, permissions }: { page: NavigationPage; scope?: string; permissions?: string[] }) {
  switch (page.key) {
    case "pmc_wfs_pending_packing":
      return <PendingPackingPage page={page} scope={scope} permissions={permissions} />;
    case "pmc_wfs_board":
      return <ShipmentBoardPage page={page} scope={scope} />;
    case "pmc_wfs_exceptions":
      return <ExceptionCenterPage page={page} scope={scope} />;
    case "pmc_wfs_settings":
    case "pmc_wfs_settings_fc":
    case "pmc_wfs_settings_defaults":
    case "pmc_wfs_settings_channels":
    case "pmc_wfs_settings_stores":
    case "pmc_wfs_settings_notes":
      return <WfsSettingsPage page={page} scope={scope} permissions={permissions} />;
    default:
      return null;
  }
}

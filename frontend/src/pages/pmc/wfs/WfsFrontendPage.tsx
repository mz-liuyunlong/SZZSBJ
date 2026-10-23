/** Routes each WFS sidebar page to its preview screen. */
import type { NavigationPage } from "@/config/navigation";
import PendingPackingPage from "./PendingPackingPage";
import ShipmentBoardPage from "./ShipmentBoardPage";
import SystemShipmentPage from "./SystemShipmentPage";
import { CreateBoardPage, ExceptionCenterPage, ProbeListPage, WfsSettingsPage } from "./WfsSupportPages";

export default function WfsFrontendPage({ page, scope, permissions }: { page: NavigationPage; scope?: string; permissions?: string[] }) {
  switch (page.key) {
    case "pmc_wfs_pending_packing":
      return <PendingPackingPage page={page} scope={scope} permissions={permissions} />;
    case "pmc_wfs_shipments":
      return <SystemShipmentPage page={page} />;
    case "pmc_wfs_probe":
      return <ProbeListPage page={page} />;
    case "pmc_wfs_create_board":
      return <CreateBoardPage page={page} />;
    case "pmc_wfs_board":
      return <ShipmentBoardPage page={page} />;
    case "pmc_wfs_exceptions":
      return <ExceptionCenterPage page={page} />;
    case "pmc_wfs_settings":
      return <WfsSettingsPage page={page} />;
    default:
      return null;
  }
}
